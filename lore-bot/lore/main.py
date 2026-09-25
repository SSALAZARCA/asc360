"""Lore's process entrypoint.

Phase 9 registers the real handlers on top of Phase 8's inert skeleton, and
Phase 10 adds the capture/correction handlers on top of that:
- `/start` begins the self-registration conversation (`handlers/registro.py`).
- `/vincular <codigo>` links an ADMIN's Telegram account (`handlers/admin.py`).
- The `lore_(apr|rej):<usuario_id>` callback buttons resolve a pending
  registration (also `handlers/admin.py`).
- `/registrar` begins the manual lost-sale capture conversation
  (`handlers/captura.py`).
- `/correcciones` begins the today-only self-service correction menu
  (`handlers/correccion.py`).
- The persistent Reply Keyboard's 2 button labels (`handlers/_common.py`,
  shown to an approved advisor after `/start`) are wired here as EXTRA
  `MessageHandler` entry points into the SAME `captura`/`correccion`
  `ConversationHandler`s their `/registrar`/`/correcciones` commands already
  use -- tapping a button behaves identically to typing the command.

Running this module for real, via the Dockerfile's `CMD`, would call
`run_polling()` and needs a live bot token; nothing here requires that to
import or unit-test (see `tests/test_main.py`, which never calls `main()`).
"""
from __future__ import annotations

import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from lore import config
from lore.estados import CapturaEstado, CorreccionEstado, RegistroEstado
from lore.handlers import admin as admin_handlers
from lore.handlers import captura as captura_handlers
from lore.handlers import correccion as correccion_handlers
from lore.handlers import registro as registro_handlers
from lore.handlers._common import BOTON_CORRECCIONES, BOTON_REGISTRAR

logger = logging.getLogger("lore.main")


def _build_registro_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", registro_handlers.start)],
        states={
            RegistroEstado.NOMBRE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, registro_handlers.recibir_nombre)
            ],
            RegistroEstado.CELULAR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, registro_handlers.recibir_celular)
            ],
            RegistroEstado.SUCURSAL: [
                CallbackQueryHandler(registro_handlers.recibir_sucursal, pattern=r"^lore_sucursal:")
            ],
            RegistroEstado.CONFIRMAR: [
                CallbackQueryHandler(registro_handlers.confirmar, pattern=r"^lore_reg_(confirmar|cancelar)$")
            ],
        },
        fallbacks=[CommandHandler("cancelar", registro_handlers.cancelar)],
        allow_reentry=True,
    )


def _build_captura_conversation() -> ConversationHandler:
    """Phase 10 — manual lost-sale capture (`/registrar`, design D7's
    `CAP_*` states, Method A only; Method B/photo extends this "from
    CAP_SELECCION onward" in Phase 11)."""
    return ConversationHandler(
        entry_points=[
            CommandHandler("registrar", captura_handlers.iniciar),
            # UX shortcut: the persistent Reply Keyboard button (see
            # `handlers/_common.py::TECLADO_ASESOR`) is an alternate entry
            # point into the SAME `iniciar` -- never a duplicated copy of its
            # logic. `filters.Text([...])` matches the message text EXACTLY,
            # same as `BOTON_REGISTRAR`'s own definition.
            MessageHandler(filters.Text([BOTON_REGISTRAR]), captura_handlers.iniciar),
        ],
        states={
            CapturaEstado.SUCURSAL: [
                CallbackQueryHandler(captura_handlers.recibir_sucursal, pattern=r"^lore_cap_suc:")
            ],
            CapturaEstado.METODO: [
                CallbackQueryHandler(captura_handlers.recibir_metodo, pattern=r"^lore_cap_metodo:")
            ],
            CapturaEstado.MANUAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, captura_handlers.recibir_codigos)
            ],
            CapturaEstado.NO_RESUELTAS: [
                CallbackQueryHandler(captura_handlers.descartar_no_resuelta, pattern=r"^lore_cap_descartar:"),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, captura_handlers.recibir_correccion_no_resueltas
                ),
            ],
            CapturaEstado.SELECCION: [
                CallbackQueryHandler(captura_handlers.alternar_seleccion, pattern=r"^lore_cap_toggle:"),
                CallbackQueryHandler(captura_handlers.continuar_seleccion, pattern=r"^lore_cap_continuar$"),
            ],
            CapturaEstado.CANTIDAD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, captura_handlers.recibir_cantidad)
            ],
            CapturaEstado.CONFIRMAR: [
                CallbackQueryHandler(captura_handlers.confirmar, pattern=r"^lore_cap_(confirmar|cancelar)$")
            ],
        },
        fallbacks=[CommandHandler("cancelar", captura_handlers.cancelar)],
        allow_reentry=True,
    )


def _build_correccion_conversation() -> ConversationHandler:
    """Phase 10 — today-only self-service correction menu (`/correcciones`,
    design D4/D7's `COR_*` states)."""
    return ConversationHandler(
        entry_points=[
            CommandHandler("correcciones", correccion_handlers.iniciar),
            # Same UX-shortcut pattern as `_build_captura_conversation` above.
            MessageHandler(filters.Text([BOTON_CORRECCIONES]), correccion_handlers.iniciar),
        ],
        states={
            CorreccionEstado.LISTA: [
                CallbackQueryHandler(correccion_handlers.seleccionar_carga, pattern=r"^lore_cor_carga:")
            ],
            CorreccionEstado.ACCION: [
                CallbackQueryHandler(correccion_handlers.elegir_linea, pattern=r"^lore_cor_linea:"),
                CallbackQueryHandler(correccion_handlers.pedir_confirmacion_anular, pattern=r"^lore_cor_anular:"),
                CallbackQueryHandler(correccion_handlers.volver_a_lista, pattern=r"^lore_cor_volver$"),
            ],
            CorreccionEstado.CANTIDAD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, correccion_handlers.recibir_cantidad)
            ],
            CorreccionEstado.CONFIRMAR_ANULAR: [
                CallbackQueryHandler(
                    correccion_handlers.resolver_confirmacion_anular,
                    pattern=r"^lore_cor_anular_(confirmar|cancelar)",
                )
            ],
        },
        fallbacks=[CommandHandler("cancelar", correccion_handlers.cancelar)],
        allow_reentry=True,
    )


async def _manejar_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler (Phase 9 fix-up, finding #3) — defense-in-depth
    so ANY future unhandled exception in a handler is at least logged and
    visible, instead of being silently swallowed by python-telegram-bot's
    default behavior. Deliberately simple: log and return, no user-facing
    recovery beyond what each handler already does on its own."""
    logger.error("Excepción no manejada procesando %r", update, exc_info=context.error)


def build_application() -> Application:
    """Construct, but do not start, the python-telegram-bot `Application`.

    No `concurrent_updates=True` is passed here, so updates are processed
    sequentially (python-telegram-bot's default) — this is load-bearing for
    `captura.confirmar`'s double-tap safety: a duplicate "Confirmar" tap
    can never race a still-in-flight `confirmar()` call for the same chat,
    because the second update is only dispatched after the first finishes.
    If a future change ever sets `concurrent_updates=True`, this safety
    disappears silently and needs its own test coverage (none exists today).
    """
    application = Application.builder().token(config.LORE_BOT_TOKEN).build()

    application.add_handler(_build_registro_conversation())
    application.add_handler(CommandHandler("vincular", admin_handlers.vincular_command))
    application.add_handler(
        CallbackQueryHandler(admin_handlers.resolver_solicitud_callback, pattern=r"^lore_(apr|rej):")
    )
    application.add_handler(_build_captura_conversation())
    application.add_handler(_build_correccion_conversation())
    # MUST be added last, in this SAME default group (group=0) — see
    # `registro.callback_huerfano`'s docstring for why a higher group number
    # (e.g. group=1) would NOT give the intended "only fires if nothing else
    # already matched" behavior (Phase 9 fix-up, finding #7).
    application.add_handler(
        CallbackQueryHandler(registro_handlers.callback_huerfano, pattern=r"^lore_")
    )

    application.add_error_handler(_manejar_error)

    return application


def main() -> None:  # pragma: no cover — exercised only by the real process
    application = build_application()
    application.run_polling()


if __name__ == "__main__":  # pragma: no cover
    main()
