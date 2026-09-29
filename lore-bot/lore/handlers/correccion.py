"""Today-only self-service correction menu (design D4/D7's `COR_*` states):
list the advisor's own registrations made today, edit a line's quantity, or
cancel an entire registration.

**Entry-point interpretation (flagged, same caveat as `captura.py`)**:
`/correcciones` is chosen — no literal command name is specified by the
spec/design.

The bot's job here is strictly to present the list and route the chosen
action: ownership + same-day-only enforcement is the BACKEND's job
(`_validar_ventana_propia`/`FUERA_DE_VENTANA`/404s in
`backend/app/motored/api/bot_demanda_perdida.py`), never re-implemented
client-side — same "server is the real gate" pattern as Phase 9's admin
approval flow. The bot only re-fetches `GET /demanda-perdida/hoy` at the
start of each menu visit; it never assumes its own cached list is still
accurate once a mutating action (edit/anular) has been taken.
"""
from __future__ import annotations

import logging
import uuid

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from lore.api import (
    BackendClient,
    CargaNoEncontrada,
    FueraDeVentana,
    LineaAnulada,
    LineaNoEncontrada,
    LoreApiError,
    NoRegistrado,
    Pendiente,
    Rechazado,
    YaAnulada,
)
from lore.estados import CorreccionEstado
from lore.handlers._asesor import (
    MSG_ASESOR_NO_DISPONIBLE,
    MSG_QUIEN_REGISTRA,
    MSG_SIN_ASESOR_HABILITADO,
    actor_automatico,
    asesores_utilizables,
    buscar_asesor,
    ninguno_habilitado,
    teclado_asesores,
    verificar_actor,
)
from lore.handlers._common import (
    _CANTIDAD_MAXIMA,
    _CANTIDAD_MINIMA,
    _MSG_CONEXION,
    _validar_cantidad,
    con_cancelar,
    editar_o_ignorar_sin_cambios,
    responder,
    responder_cancelacion,
    teclado_solo_cancelar,
)

logger = logging.getLogger("lore.handlers.correccion")

_DATA_KEY = "lore_correccion"
_ASESORES_KEY = "lore_correccion_asesores"
_PREFIJO_ASESOR = "lore_cor_ase:"


def _cliente(telegram_id: int, usuario_id: str | None = None) -> BackendClient:
    """Same seam as the other handler modules' `_cliente`. `usuario_id` is
    the advisor chosen for this conversation (shared Telegram)."""
    return BackendClient(telegram_id, usuario_id=usuario_id)


def _usuario_id(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """The advisor chosen for THIS conversation, if any; tolerant of a
    missing state (stale button after a restart)."""
    return context.user_data.get(_DATA_KEY, {}).get("usuario_id")


def _estado(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.user_data[_DATA_KEY]


def _uuid_valido(crudo: str) -> str | None:
    """Validates a callback_data-derived id BEFORE it reaches URL
    construction (same discipline as `admin.py::resolver_solicitud_callback`'s
    `usuario_id` check) — callback_data is bot-authored, not user-invented,
    but a malformed/stale value must never be string-formatted straight into
    a request path."""
    try:
        uuid.UUID(crudo)
    except ValueError:
        return None
    return crudo


async def iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """`/correcciones` — entry point. Asks "¿Quién registra?" when the
    Telegram has several usable advisors (every time, never remembered),
    then lists only the acting advisor's registrations of today."""
    telegram_id = update.effective_user.id
    async with _cliente(telegram_id) as client:
        yo = await verificar_actor(client, update)
    if yo is None:
        return ConversationHandler.END
    if ninguno_habilitado(yo):
        await update.message.reply_text(MSG_SIN_ASESOR_HABILITADO)
        return ConversationHandler.END

    usables = asesores_utilizables(yo)
    if len(usables) > 1:
        context.user_data.pop(_DATA_KEY, None)
        context.user_data[_ASESORES_KEY] = {a["id"]: a for a in usables}
        await update.message.reply_text(
            MSG_QUIEN_REGISTRA, reply_markup=teclado_asesores(_PREFIJO_ASESOR, usables)
        )
        return CorreccionEstado.ASESOR
    _, usuario_id = actor_automatico(yo)
    return await _abrir_lista(update, context, usuario_id)


async def recibir_asesor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """The tapped advisor is only accepted if it was offered in THIS
    conversation; the backend re-checks that it belongs to the Telegram."""
    query = update.callback_query
    await query.answer()

    opciones = context.user_data.pop(_ASESORES_KEY, {})
    asesor = buscar_asesor(opciones, query.data.replace(_PREFIJO_ASESOR, ""))
    if asesor is None:
        logger.warning("recibir_asesor (correccion): asesor no ofrecido %r", query.data)
        await query.edit_message_text(MSG_ASESOR_NO_DISPONIBLE)
        return ConversationHandler.END
    return await _abrir_lista(update, context, asesor["id"])


async def _abrir_lista(
    update: Update, context: ContextTypes.DEFAULT_TYPE, usuario_id: str | None
) -> int:
    telegram_id = update.effective_user.id
    async with _cliente(telegram_id, usuario_id) as client:
        try:
            cargas = await client.listar_hoy()
        except NoRegistrado:
            await responder(update, "No estás registrado todavía. Mandá /start para solicitar acceso.")
            return ConversationHandler.END
        except Pendiente:
            await responder(update, "⏳ Tu solicitud de acceso todavía está pendiente de aprobación.")
            return ConversationHandler.END
        except Rechazado:
            await responder(update, "❌ Tu solicitud de acceso fue rechazada. Contactá a un administrador.")
            return ConversationHandler.END
        except LoreApiError:
            # Includes BackendCaido.
            await responder(update, _MSG_CONEXION)
            return ConversationHandler.END

    if not cargas:
        await responder(update, "No tenés registros de hoy para corregir.")
        return ConversationHandler.END

    context.user_data[_DATA_KEY] = {"cargas": {c["carga_id"]: c for c in cargas}, "usuario_id": usuario_id}
    await responder(update, "🧾 Tus registros de hoy:", reply_markup=con_cancelar(_teclado_lista(cargas)))
    return CorreccionEstado.LISTA


def _teclado_lista(cargas: list[dict]) -> InlineKeyboardMarkup:
    filas = []
    for carga in cargas:
        sucursal = (carga.get("sucursal") or {}).get("nombre", "?")
        n = len(carga.get("lineas") or [])
        etiqueta = f"🧾 {sucursal} ({n} líneas)"
        filas.append([InlineKeyboardButton(etiqueta, callback_data=f"lore_cor_carga:{carga['carga_id']}")])
    return InlineKeyboardMarkup(filas)


async def seleccionar_carga(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    crudo = query.data.replace("lore_cor_carga:", "")
    carga_id = _uuid_valido(crudo)
    estado = _estado(context)
    carga = estado["cargas"].get(carga_id) if carga_id else None
    if carga is None:
        logger.warning("seleccionar_carga: carga_id inválido o desconocido %r", crudo)
        await query.edit_message_text("⚠️ Ese registro ya no está disponible. Mandá /correcciones de nuevo.")
        return ConversationHandler.END

    estado["carga_id_actual"] = carga_id
    return await _mostrar_acciones(update, context, carga)


_PLACEHOLDER_REFERENCIA_ELIMINADA = "(referencia eliminada)"


async def _mostrar_acciones(update: Update, context: ContextTypes.DEFAULT_TYPE, carga: dict) -> int:
    filas = [
        [
            InlineKeyboardButton(
                f"✏️ {linea['referencia'].get('codigo') or _PLACEHOLDER_REFERENCIA_ELIMINADA} "
                f"(cant: {int(linea['cantidad'])})",
                callback_data=f"lore_cor_linea:{linea['linea_id']}",
            )
        ]
        for linea in carga.get("lineas") or []
    ]
    filas.append(
        [InlineKeyboardButton("🗑 Anular todo el registro", callback_data=f"lore_cor_anular:{carga['carga_id']}")]
    )
    filas.append([InlineKeyboardButton("⬅️ Volver", callback_data="lore_cor_volver")])
    await update.callback_query.edit_message_text(
        "¿Qué querés hacer con este registro?", reply_markup=con_cancelar(filas)
    )
    return CorreccionEstado.ACCION


async def volver_a_lista(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    estado = _estado(context)
    estado.pop("carga_id_actual", None)
    estado.pop("linea_id_actual", None)
    cargas = list(estado["cargas"].values())
    if not cargas:
        await query.edit_message_text("No tenés registros de hoy para corregir.")
        return ConversationHandler.END
    await query.edit_message_text("🧾 Tus registros de hoy:", reply_markup=con_cancelar(_teclado_lista(cargas)))
    return CorreccionEstado.LISTA


async def elegir_linea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    crudo = query.data.replace("lore_cor_linea:", "")
    linea_id = _uuid_valido(crudo)
    if linea_id is None:
        logger.warning("elegir_linea: linea_id malformado %r", crudo)
        await query.edit_message_text("⚠️ No pude procesar esa línea. Mandá /correcciones de nuevo.")
        return ConversationHandler.END

    _estado(context)["linea_id_actual"] = linea_id
    await query.edit_message_text(
        f"🔢 Nueva cantidad (1 a {_CANTIDAD_MAXIMA})?", reply_markup=teclado_solo_cancelar()
    )
    return CorreccionEstado.CANTIDAD


async def recibir_cantidad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    estado = _estado(context)
    linea_id = estado.get("linea_id_actual")
    if linea_id is None:
        # gga finding: every other handler in this module validates an id
        # before building a request path (`_uuid_valido`); this one skipped
        # that check entirely -- a missing `linea_id_actual` would have sent
        # a literal "/demanda-perdida/lineas/None" request. Unreachable via
        # PTB's own state tracking under normal use, but defend anyway
        # rather than trust that invariant silently.
        logger.warning("recibir_cantidad: linea_id_actual ausente en el estado")
        _limpiar(context)
        await update.message.reply_text("⚠️ Tu sesión anterior expiró. Mandá /correcciones de nuevo.")
        return ConversationHandler.END

    texto = (update.message.text or "").strip()
    cantidad = _validar_cantidad(texto)
    if cantidad is None:
        await update.message.reply_text(
            f"Cantidad inválida. Ingresá un número entre {_CANTIDAD_MINIMA} y {_CANTIDAD_MAXIMA}.",
            reply_markup=teclado_solo_cancelar(),
        )
        return CorreccionEstado.CANTIDAD

    telegram_id = update.effective_user.id
    async with _cliente(telegram_id, _usuario_id(context)) as client:
        try:
            await client.editar_linea(linea_id, cantidad)
        except LineaNoEncontrada:
            await update.message.reply_text(
                "⚠️ No encontré esa línea (¿ya fue corregida por otra sesión?). Mandá /correcciones de nuevo."
            )
            _limpiar(context)
            return ConversationHandler.END
        except FueraDeVentana:
            await update.message.reply_text(
                "⚠️ Ese registro ya no es de hoy, no se puede editar. Contactá a un administrador."
            )
            _limpiar(context)
            return ConversationHandler.END
        except LineaAnulada:
            await update.message.reply_text("⚠️ Esa línea ya fue anulada.")
            _limpiar(context)
            return ConversationHandler.END
        except LoreApiError:
            # Includes BackendCaido: retryable, so the state stays and the
            # reply keeps the Cancelar button.
            await update.message.reply_text(_MSG_CONEXION, reply_markup=teclado_solo_cancelar())
            return CorreccionEstado.CANTIDAD

    await update.message.reply_text(
        f"✅ Cantidad actualizada a {cantidad}. Mandá /correcciones de nuevo para seguir corrigiendo."
    )
    _limpiar(context)
    return ConversationHandler.END


async def pedir_confirmacion_anular(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    crudo = query.data.replace("lore_cor_anular:", "")
    carga_id = _uuid_valido(crudo)
    if carga_id is None:
        logger.warning("pedir_confirmacion_anular: carga_id malformado %r", crudo)
        await query.edit_message_text("⚠️ No pude procesar ese registro. Mandá /correcciones de nuevo.")
        return ConversationHandler.END

    _estado(context)["carga_id_actual"] = carga_id
    await query.edit_message_text(
        "⚠️ ¿Confirmás anular este registro completo? Se van a revertir todas sus cantidades.",
        reply_markup=_teclado_confirmar_anular(carga_id),
    )
    return CorreccionEstado.CONFIRMAR_ANULAR


def _teclado_confirmar_anular(carga_id: str) -> InlineKeyboardMarkup:
    """Shared by `pedir_confirmacion_anular` and the retry branches of
    `resolver_confirmacion_anular`, which stay in CONFIRMAR_ANULAR and so
    must keep the buttons (an edit without `reply_markup` drops them, T1b).
    No shared "✖️ Cancelar" row: "❌ No" already ends the conversation and
    clears the state, exactly like it."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Sí, anular", callback_data=f"lore_cor_anular_confirmar:{carga_id}"),
                InlineKeyboardButton("❌ No", callback_data="lore_cor_anular_cancelar"),
            ]
        ]
    )


async def resolver_confirmacion_anular(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "lore_cor_anular_cancelar":
        _limpiar(context)
        await query.edit_message_text("No se anuló nada. Mandá /correcciones si querés hacer otra cosa.")
        return ConversationHandler.END

    crudo = query.data.replace("lore_cor_anular_confirmar:", "")
    carga_id = _uuid_valido(crudo)
    if carga_id is None:
        logger.warning("resolver_confirmacion_anular: carga_id malformado %r", crudo)
        await query.edit_message_text("⚠️ No pude procesar ese registro. Mandá /correcciones de nuevo.")
        return ConversationHandler.END

    telegram_id = update.effective_user.id
    async with _cliente(telegram_id, _usuario_id(context)) as client:
        try:
            await client.anular_registro(carga_id)
        except CargaNoEncontrada:
            await query.edit_message_text(
                "⚠️ No encontré ese registro (¿ya fue anulado?). Mandá /correcciones de nuevo."
            )
            _limpiar(context)
            return ConversationHandler.END
        except FueraDeVentana:
            await query.edit_message_text(
                "⚠️ Ese registro ya no es de hoy, no se puede anular. Contactá a un administrador."
            )
            _limpiar(context)
            return ConversationHandler.END
        except YaAnulada:
            await query.edit_message_text("Ese registro ya estaba anulado.")
            _limpiar(context)
            return ConversationHandler.END
        except LoreApiError:
            # Includes BackendCaido (a LoreApiError subclass): both are
            # retryable, so the state and the buttons stay.
            await editar_o_ignorar_sin_cambios(
                query, _MSG_CONEXION, reply_markup=_teclado_confirmar_anular(carga_id)
            )
            return CorreccionEstado.CONFIRMAR_ANULAR

    await query.edit_message_text("✅ Registro anulado.")
    _limpiar(context)
    return ConversationHandler.END


def _limpiar(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(_DATA_KEY, None)
    context.user_data.pop(_ASESORES_KEY, None)


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _limpiar(context)
    await responder_cancelacion(update, "Listo, no se hizo ningún cambio.")
    return ConversationHandler.END
