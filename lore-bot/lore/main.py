"""Lore's process entrypoint.

Phase 9 registers the real handlers on top of Phase 8's inert skeleton:
- `/start` begins the self-registration conversation (`handlers/registro.py`).
- `/vincular <codigo>` links an ADMIN's Telegram account (`handlers/admin.py`).
- The `lore_(apr|rej):<usuario_id>` callback buttons resolve a pending
  registration (also `handlers/admin.py`).

The capture/correction conversation handlers (Phase 10+) are not wired here
yet. Running this module for real, via the Dockerfile's `CMD`, would call
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
from lore.estados import RegistroEstado
from lore.handlers import admin as admin_handlers
from lore.handlers import registro as registro_handlers

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


async def _manejar_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler (Phase 9 fix-up, finding #3) — defense-in-depth
    so ANY future unhandled exception in a handler is at least logged and
    visible, instead of being silently swallowed by python-telegram-bot's
    default behavior. Deliberately simple: log and return, no user-facing
    recovery beyond what each handler already does on its own."""
    logger.error("Excepción no manejada procesando %r", update, exc_info=context.error)


def build_application() -> Application:
    """Construct, but do not start, the python-telegram-bot `Application`."""
    application = Application.builder().token(config.LORE_BOT_TOKEN).build()

    application.add_handler(_build_registro_conversation())
    application.add_handler(CommandHandler("vincular", admin_handlers.vincular_command))
    application.add_handler(
        CallbackQueryHandler(admin_handlers.resolver_solicitud_callback, pattern=r"^lore_(apr|rej):")
    )
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
