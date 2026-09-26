"""Lost-sale capture conversation (design D7's `CAP_*` states) — manual entry
(Method A) and, since Phase 11, photo/vision entry (Method B). Method B
reuses this module's OWN `_resolver_y_actualizar_borrador`/`_mostrar_
no_resueltas`/`_mostrar_seleccion` pipeline (see `recibir_foto`) rather than
duplicating it — exactly the design this module's `CapturaEstado.METODO`
state was built to support back in Phase 10.

**Entry-point interpretation (flagged — the design/spec are mechanism-
agnostic about the exact Telegram trigger)**: neither the spec nor design D7
names a literal command/button for starting a capture. `/registrar` is
chosen here, mirroring this project's existing Spanish, verb-based command
names (`/start`, `/vincular`, `/cancelar`).

**Sucursal source (load-bearing, do not "fix")**: `GET /yo`'s own
`sucursales` field is a bare list of ids (`actor.sucursal_ids`, per
`backend/app/motored/api/bot.py`), NOT `{id, nombre}` objects — Phase 5's
own notes flagged this ("`/yo`'s `sucursales` is id-only"). Rendering a
named picker therefore requires ALSO calling `GET /sucursales` (all active
branches, `{id, nombre}`) and filtering it down to the ids `/yo` returned.
Using `client.sucursales()` alone would let an advisor pick a branch they
are not assigned to, which the backend would then reject with 403
`SUCURSAL_NO_AUTORIZADA` — never silently mislabeling that as a bug in
`registrar_demanda_perdida`.

**ADMIN branch (ad-hoc addition, post-Phase-10, product-owner request)**: an
ADMIN has no `usuario_sucursal` rows of its own, so the "filter down to
propios_ids" logic above does not apply to it at all — `iniciar` branches on
`/yo`'s own `role` field and shows the FULL active-sucursal picker instead
(`_obtener_sucursales_todas`), matching the backend's own role-conditional
skip of the sucursal-ownership check in `registrar_demanda_perdida`
(`backend/app/motored/api/bot_demanda_perdida.py`).
"""
from __future__ import annotations

import hashlib
import logging
from uuid import UUID

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes, ConversationHandler

from lore import vision
from lore.api import (
    BackendCaido,
    BackendClient,
    IdempotencyKeyEnUso,
    LoreApiError,
    NoRegistrado,
    Pendiente,
    ReferenciaNoEncontrada,
    Rechazado,
    RegistroInconsistente,
    SucursalNoAutorizada,
    SucursalNoEncontrada,
)
from lore.estados import Borrador, CapturaEstado, LineaBorrador
from lore.handlers._common import (
    _CANTIDAD_MAXIMA,
    _CANTIDAD_MINIMA,
    _MSG_CONEXION,
    _escapar_markdown,
    _validar_cantidad,
)

logger = logging.getLogger("lore.handlers.captura")

_DRAFT_KEY = "lore_captura"
_SUCURSALES_KEY = "lore_captura_sucursales"
_MAX_CODIGOS_POR_LOTE = 30


def _cliente(telegram_id: int) -> BackendClient:
    """Same seam as `handlers/registro.py::_cliente`/`handlers/admin.py::_cliente`."""
    return BackendClient(telegram_id)


def _borrador(context: ContextTypes.DEFAULT_TYPE) -> Borrador:
    return context.user_data[_DRAFT_KEY]


def _parsear_codigos(texto: str) -> tuple[list[str], int]:
    """Split free text into individual reference codes — comma AND newline
    separated (an advisor may paste a list either way). Blank entries are
    dropped; duplicates are removed case-insensitively (the backend's own
    `resolver_referencias` normalizes the same way, but de-duping here keeps
    the resolved-lines list from growing spuriously when a code is pasted
    twice in the same message).

    Returns `(codigos, descartados)` — `descartados` is how many distinct
    codes were dropped by the `_MAX_CODIGOS_POR_LOTE` cap (Phase 10 fix-up,
    finding #4: this used to be silent, contradicting this module's own
    "unresolved/dropped codes are always surfaced" principle). Callers must
    warn the advisor when `descartados > 0`."""
    crudos = [
        pedazo.strip()
        for linea in texto.splitlines()
        for pedazo in linea.split(",")
    ]
    vistos: set[str] = set()
    codigos: list[str] = []
    for codigo in crudos:
        if not codigo:
            continue
        clave = codigo.upper()
        if clave in vistos:
            continue
        vistos.add(clave)
        codigos.append(codigo)
    descartados = max(0, len(codigos) - _MAX_CODIGOS_POR_LOTE)
    return codigos[:_MAX_CODIGOS_POR_LOTE], descartados


def _texto_truncamiento(descartados: int) -> str:
    return (
        f"⚠️ Se ignoraron {descartados} código(s) porque superaste el máximo de "
        f"{_MAX_CODIGOS_POR_LOTE} por mensaje."
    )


def _clave_descarte(codigo: str) -> str:
    """Stable identifier for a `no_resueltas` entry, used as its discard
    button's `callback_data` — mirrors `alternar_seleccion`'s `referencia_id`
    keying (immune to the list reordering/shrinking a double-tap or a stale
    button can cause), which raw list POSITION is not (Phase 10 fix-up,
    finding #2).

    Hashed rather than the raw code: `Referencia.codigo` is an unconstrained
    `String(100)` in the backend (no CHECK/charset restriction — verified by
    reading `backend/app/motored/models/referencia.py` directly), so a `:`
    separator collision with a real code cannot be ruled out, and a 100-char
    code could exceed Telegram's own 64-byte `callback_data` limit on its
    own. A short hash sidesteps both risks."""
    return hashlib.sha256(codigo.strip().upper().encode("utf-8")).hexdigest()[:16]


async def _verificar_actor(client: BackendClient, update: Update) -> dict | None:
    """First concern split out of `iniciar` (Phase 10 fix-up, finding #7):
    re-derives `require_bot_asesor`'s gate via `client.yo()`, never assumed
    from a prior `/start` (the actor's status could have changed since).
    Replies and returns `None` when the actor can't proceed; returns `/yo`'s
    body otherwise."""
    try:
        return await client.yo()
    except NoRegistrado:
        await update.message.reply_text("No estás registrado todavía. Mandá /start para solicitar acceso.")
        return None
    except Pendiente:
        await update.message.reply_text("⏳ Tu solicitud de acceso todavía está pendiente de aprobación.")
        return None
    except Rechazado:
        await update.message.reply_text("❌ Tu solicitud de acceso fue rechazada. Contactá a un administrador.")
        return None
    except BackendCaido:
        await update.message.reply_text(_MSG_CONEXION)
        return None
    except LoreApiError:
        # Same rationale as registro.py/admin.py's final fallback: every
        # BackendClient method shares ONE global error-code map, so a
        # subclass not explicitly branched on above must still reply.
        await update.message.reply_text(_MSG_CONEXION)
        return None


async def _fetch_sucursales_o_avisar(client: BackendClient, update: Update) -> list[dict] | None:
    """Fix-up finding #4 (WARNING, readability): `_obtener_sucursales_propias`
    and `_obtener_sucursales_todas` used to each wrap `client.sucursales()`
    in the IDENTICAL `except BackendCaido`/`except LoreApiError` scaffolding
    that does the exact same thing — hoisted here so both callers share ONE
    fetch-and-error-handle step. Replies and returns `None` on failure (the
    same `_MSG_CONEXION` both call sites already used); returns the raw list
    on success. Callers apply their OWN post-filter/empty-check on top — this
    helper knows nothing about "propias" vs. "todas". Pure de-duplication, no
    behavior change."""
    try:
        return await client.sucursales()
    except BackendCaido:
        await update.message.reply_text(_MSG_CONEXION)
        return None
    except LoreApiError:
        await update.message.reply_text(_MSG_CONEXION)
        return None


async def _obtener_sucursales_propias(
    client: BackendClient, update: Update, propios_ids: set[str]
) -> list[dict] | None:
    """Second concern split out of `iniciar` (Phase 10 fix-up, finding #7):
    fetches ALL active sucursales (via `_fetch_sucursales_o_avisar`) and
    filters them down to `propios_ids` — see the module docstring for why
    `/yo` alone (id-only) can't render a named picker on its own. Replies and
    returns `None` on failure or an empty intersection."""
    todas = await _fetch_sucursales_o_avisar(client, update)
    if todas is None:
        return None

    propias = [s for s in todas if s.get("id") in propios_ids]
    if not propias:
        await update.message.reply_text(
            "⚠️ No pude encontrar tus sucursales asignadas. Contactá a un administrador."
        )
        return None
    return propias


async def _obtener_sucursales_todas(client: BackendClient, update: Update) -> list[dict] | None:
    """ADMIN counterpart of `_obtener_sucursales_propias` (ad-hoc addition,
    post-Phase-10, product-owner request). An ADMIN has NO `usuario_sucursal`
    rows of its own (unlike an advisor) — filtering `client.sucursales()`
    down to "its own" ids would always yield an empty list, the OPPOSITE of
    the request ("an admin can charge any active sucursal"). Returns EVERY
    active sucursal unfiltered (via `_fetch_sucursales_o_avisar`). Replies and
    returns `None` on failure or an empty result (no active sucursales at
    all)."""
    todas = await _fetch_sucursales_o_avisar(client, update)
    if todas is None:
        return None

    if not todas:
        await update.message.reply_text(
            "⚠️ No pude cargar la lista de sucursales en este momento. Probá de nuevo con /registrar."
        )
        return None
    return todas


async def _resolver_sucursales_y_auto_seleccion(
    client: BackendClient, update: Update, yo: dict
) -> tuple[list[dict], bool] | None:
    """Third concern split out of `iniciar` (Fix-up finding #5 — `iniciar`
    was back near the ~50-line bar after finding #4's de-duplication; this
    extracts its "get propias + decide auto_seleccionar" step). Branches on
    `/yo`'s own `role` field (never assumed, same discipline as every other
    role check in this codebase):

    - ADMIN: NO `usuario_sucursal` rows of its own — `/yo`'s `sucursales`
      field is always empty for that role, by design, not misconfiguration.
      Skips the "propios_ids" derivation/empty-check entirely and shows the
      FULL active-sucursal picker instead (`_obtener_sucursales_todas`).
      Auto-select is intentionally NEVER applied here: which sucursal to
      charge is the whole point of asking an admin, so it always gets the
      picker, even with only one active sucursal system-wide.
    - ASESOR_MOSTRADOR (or role absent, back-compat): its own assigned
      sucursales (`_obtener_sucursales_propias`), auto-selected only when
      exactly one exists — a real "no choice to make" case, unlike ADMIN's.

    Replies and returns `None` when neither branch can proceed (delegated to
    the helpers above, or this function's own "no tenés ninguna sucursal
    asignada" empty-check for a non-ADMIN with zero `propios_ids`). No
    behavior change from before this extraction."""
    es_admin = yo.get("role") == "ADMIN"
    if es_admin:
        propias = await _obtener_sucursales_todas(client, update)
        if propias is None:
            return None
        return propias, False

    propios_ids = set(yo.get("sucursales") or [])
    if not propios_ids:
        await update.message.reply_text(
            "⚠️ No tenés ninguna sucursal asignada todavía. Contactá a un administrador."
        )
        return None

    propias = await _obtener_sucursales_propias(client, update, propios_ids)
    if propias is None:
        return None
    return propias, len(propias) == 1


async def iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """`/registrar` — entry point. Auth re-check and sucursal/auto-select
    resolution are delegated to `_verificar_actor`/`_resolver_sucursales_y_
    auto_seleccion`; this function only orchestrates: verify actor -> resolve
    sucursales/auto-select -> render UI (Phase 10 fix-up, finding #7;
    Fix-up finding #5 — further decomposition, no behavior change)."""
    telegram_id = update.effective_user.id
    async with _cliente(telegram_id) as client:
        yo = await _verificar_actor(client, update)
        if yo is None:
            return ConversationHandler.END

        resultado = await _resolver_sucursales_y_auto_seleccion(client, update, yo)
        if resultado is None:
            return ConversationHandler.END
        propias, auto_seleccionar = resultado

    context.user_data[_DRAFT_KEY] = Borrador()
    if auto_seleccionar:
        _borrador(context).sucursal_id = UUID(propias[0]["id"])
        return await _pedir_metodo(update, context)

    context.user_data[_SUCURSALES_KEY] = {s["id"]: s["nombre"] for s in propias}
    kb = [[InlineKeyboardButton(s["nombre"], callback_data=f"lore_cap_suc:{s['id']}")] for s in propias]
    await update.message.reply_text(
        "🏢 ¿Para qué sucursal es esta venta perdida?", reply_markup=InlineKeyboardMarkup(kb)
    )
    return CapturaEstado.SUCURSAL


async def recibir_sucursal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    sucursal_id = query.data.replace("lore_cap_suc:", "")
    sucursales = context.user_data.get(_SUCURSALES_KEY, {})
    if sucursal_id not in sucursales:
        logger.warning("recibir_sucursal (captura): sucursal_id desconocido %r", sucursal_id)
        context.user_data.pop(_DRAFT_KEY, None)
        await query.edit_message_text("⚠️ Tu sesión anterior expiró. Mandá /registrar de nuevo.")
        return ConversationHandler.END

    _borrador(context).sucursal_id = UUID(sucursal_id)
    return await _pedir_metodo(update, context, via_callback=True)


async def _pedir_metodo(update: Update, context: ContextTypes.DEFAULT_TYPE, *, via_callback: bool = False) -> int:
    """`CapturaEstado.METODO` — Phase 10 kept this state specifically so
    Phase 11 could add the FOTO button here without reshaping the flow
    (Phase 10 ambiguity #2). Both MANUAL and FOTO now offered."""
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📝 Ingresar manualmente", callback_data="lore_cap_metodo:MANUAL")],
            [InlineKeyboardButton("📷 Sacar una foto", callback_data="lore_cap_metodo:FOTO")],
        ]
    )
    texto = "¿Cómo querés registrar la venta perdida?"
    if via_callback:
        await update.callback_query.edit_message_text(texto, reply_markup=kb)
    else:
        await update.message.reply_text(texto, reply_markup=kb)
    return CapturaEstado.METODO


_METODOS_VALIDOS = ("MANUAL", "FOTO")


async def recibir_metodo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Phase 11: branches on the tapped button. `metodo` is derived from
    `callback_data` and validated against `_METODOS_VALIDOS` before use
    (project discipline — every callback-data-derived value must be
    validated, same as `recibir_sucursal`'s own unknown-id handling) —
    a tampered or stale value ends the conversation instead of trusting
    it silently."""
    query = update.callback_query
    await query.answer()

    metodo = query.data.replace("lore_cap_metodo:", "")
    if metodo not in _METODOS_VALIDOS:
        logger.warning("recibir_metodo: método desconocido %r", metodo)
        context.user_data.pop(_DRAFT_KEY, None)
        await query.edit_message_text("⚠️ Tu sesión anterior expiró. Mandá /registrar de nuevo.")
        return ConversationHandler.END

    _borrador(context).metodo = metodo
    if metodo == "FOTO":
        await query.edit_message_text(
            "📷 Mandá una foto donde se vean los códigos de referencia."
        )
        return CapturaEstado.FOTO

    await query.edit_message_text(
        "✍️ Escribí los códigos de referencia. Podés mandar varios separados por coma o uno por línea."
    )
    return CapturaEstado.MANUAL


async def _resolver_y_actualizar_borrador(
    client: BackendClient, draft: Borrador, codigos: list[str]
) -> None:
    """Shared by `recibir_codigos` (CAP_MANUAL) and `recibir_correccion_no_resueltas`
    (CAP_NO_RESUELTAS's retype path) — resolves `codigos` against the
    backend and merges the result into `draft`: a resolved code that is
    already in `draft.lineas` (same `referencia_id`) is never duplicated; an
    unresolved code is added to `draft.no_resueltas` (also de-duplicated) —
    never silently dropped (spec's "Unresolved reference codes are
    surfaced, never dropped")."""
    resultado = await client.resolver_referencias(codigos)
    existentes = {str(linea.referencia_id) for linea in draft.lineas}
    for resuelta in resultado.get("resueltas") or []:
        referencia_id = resuelta.get("referencia_id")
        if referencia_id in existentes:
            continue
        existentes.add(referencia_id)
        draft.lineas.append(
            LineaBorrador(
                referencia_id=UUID(referencia_id),
                codigo=resuelta.get("codigo", ""),
                nombre=resuelta.get("nombre"),
            )
        )
    no_resueltas_vistas = {c.upper() for c in draft.no_resueltas}
    for entrada in resultado.get("no_resueltas") or []:
        if entrada.upper() in no_resueltas_vistas:
            continue
        no_resueltas_vistas.add(entrada.upper())
        draft.no_resueltas.append(entrada)


async def recibir_codigos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text or ""
    codigos, descartados = _parsear_codigos(texto)
    if not codigos:
        await update.message.reply_text("No reconocí ningún código ahí. Escribí al menos uno.")
        return CapturaEstado.MANUAL
    if descartados:
        await update.message.reply_text(_texto_truncamiento(descartados))

    draft = _borrador(context)
    telegram_id = update.effective_user.id
    async with _cliente(telegram_id) as client:
        try:
            await _resolver_y_actualizar_borrador(client, draft, codigos)
        except BackendCaido:
            await update.message.reply_text(_MSG_CONEXION)
            return CapturaEstado.MANUAL
        except LoreApiError:
            await update.message.reply_text(_MSG_CONEXION)
            return CapturaEstado.MANUAL

    if draft.no_resueltas:
        return await _mostrar_no_resueltas(update, context)
    if not draft.lineas:
        await update.message.reply_text("No reconocí ningún código ahí. Escribí al menos uno.")
        return CapturaEstado.MANUAL
    return await _mostrar_seleccion(update, context)


async def recibir_foto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """`CapturaEstado.FOTO` — Method B (photo) entry (task 11.6). Downloads
    the highest-resolution `PhotoSize` (`update.message.photo[-1]`,
    python-telegram-bot's own "smallest-to-largest" convention, verified
    against `python-telegram-bot>=21.3`'s API, not assumed from an older
    version) and hands it to `lore.vision.extraer_referencias`.

    **Three distinct failure modes (judgment call, flagged)**:
    - `TelegramError` from `photo.get_file()` itself (gga post-fix-up
      finding: this Telegram network call happened BEFORE the try/except
      that already covered `vision.extraer_referencias`, so a `NetworkError`/
      `TimedOut`/expired-`file_id` `BadRequest` here used to escape unhandled
      — now caught alongside `VisionError` below, same fallback).
    - `VisionError` (the OpenAI call itself failed after retries, OR the
      Telegram download inside `vision.extraer_referencias` failed): falls
      back FULLY to manual entry — a distinct, generic error message, then
      `CapturaEstado.MANUAL`, since typing is the advisor's only path
      forward at that point.
    - An EMPTY candidate list (a SUCCESSFUL call recognizing nothing): a
      DIFFERENT, milder outcome — a distinct "no reconocí nada" message,
      staying in `CapturaEstado.FOTO` so the advisor can either retry with
      another photo or switch to typing codes directly (this state accepts
      BOTH input types — see `main.py`'s wiring for `CapturaEstado.FOTO`).

    A non-empty candidate list is resolved through the EXACT SAME
    `_resolver_y_actualizar_borrador` helper manual entry uses (task 11.6:
    never a second implementation of that pipeline) — only each candidate's
    `codigo` is sent to the backend; vision's own `nombre` is display-only
    and is discarded here, exactly like `resolver_referencias`'s response
    already replaces it with the master `Referencia.nombre` for resolved
    items."""
    draft = _borrador(context)
    photo = update.message.photo[-1]

    try:
        file = await photo.get_file()
        # Fix-up finding #4 (WARNING, resilience): an immediate
        # acknowledgement before the (potentially slow) vision call —
        # without it, an advisor with no feedback is likely to re-send the
        # photo or tap other buttons, generating extra queued updates on a
        # bot that dispatches sequentially.
        await update.message.reply_text("📷 Analizando la foto...")
        candidatos = await vision.extraer_referencias(file)
    except (TelegramError, vision.VisionError):
        logger.warning("recibir_foto: no se pudo procesar la foto, cayendo a entrada manual")
        await update.message.reply_text(
            "⚠️ No pude analizar esa foto. Escribí los códigos de referencia a mano."
        )
        return CapturaEstado.MANUAL

    if not candidatos:
        await update.message.reply_text(
            "🔍 No reconocí ninguna referencia en esa foto. Probá con otra foto más clara, "
            "o escribí los códigos a mano."
        )
        return CapturaEstado.FOTO

    codigos = [candidato.codigo for candidato in candidatos]
    telegram_id = update.effective_user.id
    async with _cliente(telegram_id) as client:
        try:
            await _resolver_y_actualizar_borrador(client, draft, codigos)
        except BackendCaido:
            await update.message.reply_text(_MSG_CONEXION)
            return CapturaEstado.FOTO
        except LoreApiError:
            await update.message.reply_text(_MSG_CONEXION)
            return CapturaEstado.FOTO

    if draft.no_resueltas:
        return await _mostrar_no_resueltas(update, context)
    if not draft.lineas:
        await update.message.reply_text(
            "No reconocí ningún código válido ahí. Escribí los códigos a mano."
        )
        return CapturaEstado.MANUAL
    return await _mostrar_seleccion(update, context)


async def _mostrar_no_resueltas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _borrador(context)
    lineas_texto = "\n".join(f"• {_escapar_markdown(codigo)}" for codigo in draft.no_resueltas)
    kb = [
        [
            InlineKeyboardButton(
                f"🗑 Descartar {codigo}", callback_data=f"lore_cap_descartar:{_clave_descarte(codigo)}"
            )
        ]
        for codigo in draft.no_resueltas
    ]
    texto = (
        "⚠️ *No encontré estas referencias:*\n\n"
        f"{lineas_texto}\n\n"
        "Podés descartarlas o escribir de nuevo los códigos corregidos."
    )
    if update.callback_query is not None:
        await update.callback_query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return CapturaEstado.NO_RESUELTAS


async def descartar_no_resuelta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    draft = _borrador(context)
    clave = query.data.replace("lore_cap_descartar:", "")
    indice_a_borrar = next(
        (i for i, codigo in enumerate(draft.no_resueltas) if _clave_descarte(codigo) == clave),
        None,
    )
    if indice_a_borrar is None:
        # gga finding: a stale/duplicate tap (e.g. the list already shrank
        # since this button was rendered, or the code it pointed at was
        # already discarded by an earlier tap) must NOT re-render
        # `_mostrar_no_resueltas` here -- the list is unchanged, so Telegram
        # rejects an `edit_message_text` with identical content/keyboard as
        # `BadRequest: message is not modified`. Answering the toast is
        # enough feedback; never guess at a different entry, matching this
        # module's own invariant that unresolved codes are never dropped
        # without the advisor's intent. Also: only ONE `answer()` per
        # callback query is allowed -- do not call it again below.
        logger.warning("descartar_no_resuelta: clave desconocida o ya descartada %r", clave)
        await query.answer("Ese ítem ya no está en la lista.", show_alert=False)
        return CapturaEstado.NO_RESUELTAS

    await query.answer()
    draft.no_resueltas.pop(indice_a_borrar)
    if draft.no_resueltas:
        return await _mostrar_no_resueltas(update, context)
    if not draft.lineas:
        await query.edit_message_text("Ya no queda ninguna referencia. Escribí los códigos de nuevo.")
        return CapturaEstado.MANUAL
    return await _mostrar_seleccion(update, context)


async def recibir_correccion_no_resueltas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """CAP_NO_RESUELTAS's retype path — the advisor sends corrected text
    instead of tapping a discard button."""
    texto = update.message.text or ""
    codigos, descartados = _parsear_codigos(texto)
    if not codigos:
        return await _mostrar_no_resueltas(update, context)
    if descartados:
        await update.message.reply_text(_texto_truncamiento(descartados))

    draft = _borrador(context)
    # Any of these newly-typed codes might correct a previously unresolved
    # entry — resolving again will either re-add it to `no_resueltas`
    # (still wrong) or move it into `lineas` (fixed). The stale entries for
    # codes NOT re-typed this round are intentionally left untouched.
    resueltos_antes = {c.upper() for c in codigos}
    draft.no_resueltas = [c for c in draft.no_resueltas if c.upper() not in resueltos_antes]

    telegram_id = update.effective_user.id
    async with _cliente(telegram_id) as client:
        try:
            await _resolver_y_actualizar_borrador(client, draft, codigos)
        except BackendCaido:
            await update.message.reply_text(_MSG_CONEXION)
            return CapturaEstado.NO_RESUELTAS
        except LoreApiError:
            await update.message.reply_text(_MSG_CONEXION)
            return CapturaEstado.NO_RESUELTAS

    if draft.no_resueltas:
        return await _mostrar_no_resueltas(update, context)
    if not draft.lineas:
        await update.message.reply_text("Ya no queda ninguna referencia. Escribí los códigos de nuevo.")
        return CapturaEstado.MANUAL
    return await _mostrar_seleccion(update, context)


def _teclado_seleccion(draft: Borrador) -> InlineKeyboardMarkup:
    filas = [
        [
            InlineKeyboardButton(
                f"{'✅' if linea.seleccionada else '⬜'} {linea.codigo}",
                callback_data=f"lore_cap_toggle:{linea.referencia_id}",
            )
        ]
        for linea in draft.lineas
    ]
    filas.append([InlineKeyboardButton("▶️ Continuar", callback_data="lore_cap_continuar")])
    return InlineKeyboardMarkup(filas)


async def _mostrar_seleccion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _borrador(context)
    texto = "📋 Tocá cada referencia para seleccionarla (empiezan todas sin marcar):"
    kb = _teclado_seleccion(draft)
    if update.callback_query is not None:
        await update.callback_query.edit_message_text(texto, reply_markup=kb)
    else:
        await update.message.reply_text(texto, reply_markup=kb)
    return CapturaEstado.SELECCION


async def alternar_seleccion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    draft = _borrador(context)
    referencia_id = query.data.replace("lore_cap_toggle:", "")
    for linea in draft.lineas:
        if str(linea.referencia_id) == referencia_id:
            linea.seleccionada = not linea.seleccionada
            break
    else:
        # gga finding: nothing changed, so re-editing the reply markup with
        # the SAME keyboard raises `BadRequest: message is not modified`.
        # Return without editing. `query.answer()` was already sent
        # unconditionally above -- Telegram allows only ONE per callback
        # query, so no second `answer()` call belongs here either.
        logger.warning("alternar_seleccion: referencia_id desconocido %r", referencia_id)
        return CapturaEstado.SELECCION

    await query.edit_message_reply_markup(reply_markup=_teclado_seleccion(draft))
    return CapturaEstado.SELECCION


def _siguiente_sin_cantidad(draft: Borrador) -> LineaBorrador | None:
    for linea in draft.lineas:
        if linea.seleccionada and linea.cantidad is None:
            return linea
    return None


async def continuar_seleccion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    draft = _borrador(context)
    if not any(linea.seleccionada for linea in draft.lineas):
        # gga finding: Telegram accepts only ONE `answer()` per callback
        # query — a second call raises an uncaught `BadRequest`. Answer
        # ONCE, with the alert, on this path (never both an empty answer
        # AND a follow-up alert answer for the same tap).
        await query.answer("Seleccioná al menos una referencia antes de continuar.", show_alert=True)
        return CapturaEstado.SELECCION

    await query.answer()

    pendiente = _siguiente_sin_cantidad(draft)
    if pendiente is None:
        return await _mostrar_confirmacion(update, context)

    await query.edit_message_text(_texto_pedido_cantidad(pendiente), parse_mode="Markdown")
    return CapturaEstado.CANTIDAD


def _texto_pedido_cantidad(linea: LineaBorrador) -> str:
    nombre = f" ({_escapar_markdown(linea.nombre)})" if linea.nombre else ""
    return f"🔢 Cantidad para *{_escapar_markdown(linea.codigo)}*{nombre}? (1 a {_CANTIDAD_MAXIMA})"


async def recibir_cantidad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _borrador(context)
    pendiente = _siguiente_sin_cantidad(draft)
    if pendiente is None:
        # Defensive: nothing left to ask, e.g. a duplicate/stray message —
        # never silently accept a quantity with no target line.
        return await _mostrar_confirmacion(update, context)

    texto = (update.message.text or "").strip()
    cantidad = _validar_cantidad(texto)
    if cantidad is None:
        await update.message.reply_text(
            f"Cantidad inválida. Ingresá un número entre {_CANTIDAD_MINIMA} y {_CANTIDAD_MAXIMA} "
            f"para {pendiente.codigo}."
        )
        return CapturaEstado.CANTIDAD

    pendiente.cantidad = cantidad
    siguiente = _siguiente_sin_cantidad(draft)
    if siguiente is not None:
        await update.message.reply_text(_texto_pedido_cantidad(siguiente), parse_mode="Markdown")
        return CapturaEstado.CANTIDAD
    return await _mostrar_confirmacion(update, context)


async def _mostrar_confirmacion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _borrador(context)
    seleccionadas = [linea for linea in draft.lineas if linea.seleccionada]
    filas = "\n".join(
        f"• {_escapar_markdown(linea.codigo)} — {linea.cantidad}" for linea in seleccionadas
    )
    texto = f"📋 *Confirmá el registro:*\n\n{filas}\n\n¿Confirmás el envío?"
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Confirmar", callback_data="lore_cap_confirmar"),
                InlineKeyboardButton("❌ Cancelar", callback_data="lore_cap_cancelar"),
            ]
        ]
    )
    if update.callback_query is not None:
        await update.callback_query.edit_message_text(texto, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(texto, parse_mode="Markdown", reply_markup=kb)
    return CapturaEstado.CONFIRMAR


async def _enviar_registro(client: BackendClient, draft: Borrador) -> dict:
    """Payload-building + submit, split out of `confirmar` (Phase 10 fix-up,
    finding #7) — raises the SAME typed errors `confirmar` already handles;
    this function does no UI/state work at all."""
    lineas_payload = [
        {"referencia_id": str(linea.referencia_id), "cantidad": linea.cantidad}
        for linea in draft.lineas
        if linea.seleccionada
    ]
    return await client.registrar_demanda_perdida(
        sucursal_id=str(draft.sucursal_id),
        metodo=draft.metodo or "MANUAL",
        lineas=lineas_payload,
        idempotency_key=str(draft.registro_id),
    )


_MSG_CONFIRMAR_REINTENTO = (
    "⚠️ Tuve un problema para confirmar el registro. Tocá Confirmar de nuevo para reintentar."
)

# gga finding: `confirmar` had 6 separate `except` branches, 4 of which
# were structurally identical (edit message -> _limpiar_borrador -> END) --
# merged into one dispatch table + one `except` clause (Phase 10 fix-up
# follow-up). Only the message text differs per error type.
_MENSAJES_ERROR_TERMINAL: dict[type[LoreApiError], str] = {
    SucursalNoAutorizada: "⚠️ Tu sucursal ya no está autorizada para este registro. Mandá /registrar de nuevo.",
    ReferenciaNoEncontrada: "⚠️ Una referencia o sucursal ya no existe. Mandá /registrar de nuevo.",
    SucursalNoEncontrada: "⚠️ Una referencia o sucursal ya no existe. Mandá /registrar de nuevo.",
    IdempotencyKeyEnUso: "⚠️ Este registro ya fue procesado por otra sesión. Mandá /registrar de nuevo si hace falta.",
}


async def confirmar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Interprets `_enviar_registro`'s outcome into UI text/state (Phase 10
    fix-up, finding #7 — decomposition; finding #1 — CRITICAL retry fix).

    **`BackendCaido`/`LoreApiError` fix (finding #1)**: these branches used
    to `ConversationHandler.END` and were the ONLY two outcomes here that did
    NOT clear the draft — an inconsistency that was actually a bug: ending
    the conversation forces any retry through a fresh `/registrar`, which
    mints a NEW `Borrador`/`registro_id` (the `Idempotency-Key`). If the
    original `POST /demanda-perdida` actually committed backend-side but the
    response was lost to a network timeout, a fresh key turns an AMBIGUOUS
    outcome into a GUARANTEED duplicate lost-sale record — the backend's own
    idempotent-replay safety net (`registrar_demanda_perdida`'s docstring:
    "200 on an idempotent replay by the SAME actor") never gets a chance to
    kick in, because a different key can never match the original request.
    Staying in `CapturaEstado.CONFIRMAR` against the SAME draft (mirroring
    `correccion.py`'s own `BackendCaido` branches, which already stay in
    their current state) lets a duplicate "Confirmar" tap safely replay with
    the SAME key instead."""
    query = update.callback_query
    await query.answer()

    if query.data == "lore_cap_cancelar":
        await query.edit_message_text("Registro cancelado. Si querés intentarlo de nuevo, mandá /registrar.")
        _limpiar_borrador(context)
        return ConversationHandler.END

    draft = _borrador(context)
    telegram_id = update.effective_user.id
    async with _cliente(telegram_id) as client:
        try:
            await _enviar_registro(client, draft)
        except (SucursalNoAutorizada, ReferenciaNoEncontrada, SucursalNoEncontrada, IdempotencyKeyEnUso) as exc:
            await query.edit_message_text(_MENSAJES_ERROR_TERMINAL[type(exc)])
            _limpiar_borrador(context)
            return ConversationHandler.END
        except RegistroInconsistente:
            logger.error("confirmar (captura): REGISTRO_INCONSISTENTE para telegram_id=%s", telegram_id)
            await query.edit_message_text(_MSG_CONEXION)
            _limpiar_borrador(context)
            return ConversationHandler.END
        except BackendCaido:
            logger.error(
                "confirmar (captura): BackendCaido para telegram_id=%s, registro_id=%s — "
                "manteniendo el draft para reintento con la MISMA Idempotency-Key",
                telegram_id,
                draft.registro_id,
            )
            await query.edit_message_text(_MSG_CONFIRMAR_REINTENTO)
            return CapturaEstado.CONFIRMAR
        except LoreApiError:
            # Final fallback, per this project's established rule: catch the
            # base class too, since require_bot_asesor's own gate can raise
            # NoRegistrado/Pendiente/Rechazado if the actor's status changed
            # mid-conversation. Same retry treatment as BackendCaido above —
            # an unmapped error is still a transient/ambiguous outcome, not a
            # confirmed rejection.
            logger.error(
                "confirmar (captura): LoreApiError no mapeado para telegram_id=%s, registro_id=%s",
                telegram_id,
                draft.registro_id,
            )
            await query.edit_message_text(_MSG_CONFIRMAR_REINTENTO)
            return CapturaEstado.CONFIRMAR

    await query.edit_message_text("✅ *¡Registro guardado!*", parse_mode="Markdown")
    _limpiar_borrador(context)
    return ConversationHandler.END


def _limpiar_borrador(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(_DRAFT_KEY, None)
    context.user_data.pop(_SUCURSALES_KEY, None)


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _limpiar_borrador(context)
    await update.message.reply_text("Registro cancelado. Si querés intentarlo de nuevo, mandá /registrar.")
    return ConversationHandler.END
