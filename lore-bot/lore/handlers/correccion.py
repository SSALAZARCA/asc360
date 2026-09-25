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
    BackendCaido,
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
from lore.handlers._common import (
    _CANTIDAD_MAXIMA,
    _CANTIDAD_MINIMA,
    _MSG_CONEXION,
    _validar_cantidad,
)

logger = logging.getLogger("lore.handlers.correccion")

_DATA_KEY = "lore_correccion"


def _cliente(telegram_id: int) -> BackendClient:
    """Same seam as the other handler modules' `_cliente`."""
    return BackendClient(telegram_id)


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
    """`/correcciones` — entry point."""
    telegram_id = update.effective_user.id
    async with _cliente(telegram_id) as client:
        try:
            cargas = await client.listar_hoy()
        except NoRegistrado:
            await update.message.reply_text("No estás registrado todavía. Mandá /start para solicitar acceso.")
            return ConversationHandler.END
        except Pendiente:
            await update.message.reply_text("⏳ Tu solicitud de acceso todavía está pendiente de aprobación.")
            return ConversationHandler.END
        except Rechazado:
            await update.message.reply_text("❌ Tu solicitud de acceso fue rechazada. Contactá a un administrador.")
            return ConversationHandler.END
        except BackendCaido:
            await update.message.reply_text(_MSG_CONEXION)
            return ConversationHandler.END
        except LoreApiError:
            await update.message.reply_text(_MSG_CONEXION)
            return ConversationHandler.END

    if not cargas:
        await update.message.reply_text("No tenés registros de hoy para corregir.")
        return ConversationHandler.END

    context.user_data[_DATA_KEY] = {"cargas": {c["carga_id"]: c for c in cargas}}
    kb = _teclado_lista(cargas)
    await update.message.reply_text("🧾 Tus registros de hoy:", reply_markup=kb)
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
        "¿Qué querés hacer con este registro?", reply_markup=InlineKeyboardMarkup(filas)
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
    await query.edit_message_text("🧾 Tus registros de hoy:", reply_markup=_teclado_lista(cargas))
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
    await query.edit_message_text(f"🔢 Nueva cantidad (1 a {_CANTIDAD_MAXIMA})?")
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
            f"Cantidad inválida. Ingresá un número entre {_CANTIDAD_MINIMA} y {_CANTIDAD_MAXIMA}."
        )
        return CorreccionEstado.CANTIDAD

    telegram_id = update.effective_user.id
    async with _cliente(telegram_id) as client:
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
        except BackendCaido:
            await update.message.reply_text(_MSG_CONEXION)
            return CorreccionEstado.CANTIDAD
        except LoreApiError:
            await update.message.reply_text(_MSG_CONEXION)
            return CorreccionEstado.CANTIDAD

    await update.message.reply_text(
        f"✅ Cantidad actualizada a {texto}. Mandá /correcciones de nuevo para seguir corrigiendo."
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
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Sí, anular", callback_data=f"lore_cor_anular_confirmar:{carga_id}"),
                InlineKeyboardButton("❌ No", callback_data="lore_cor_anular_cancelar"),
            ]
        ]
    )
    await query.edit_message_text(
        "⚠️ ¿Confirmás anular este registro completo? Se van a revertir todas sus cantidades.",
        reply_markup=kb,
    )
    return CorreccionEstado.CONFIRMAR_ANULAR


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
    async with _cliente(telegram_id) as client:
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
        except BackendCaido:
            await query.edit_message_text(_MSG_CONEXION)
            return CorreccionEstado.CONFIRMAR_ANULAR
        except LoreApiError:
            await query.edit_message_text(_MSG_CONEXION)
            return CorreccionEstado.CONFIRMAR_ANULAR

    await query.edit_message_text("✅ Registro anulado.")
    _limpiar(context)
    return ConversationHandler.END


def _limpiar(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(_DATA_KEY, None)


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _limpiar(context)
    await update.message.reply_text("Listo, no se hizo ningún cambio.")
    return ConversationHandler.END
