from lore import config
from lore.main import build_application


def test_build_application_uses_the_configured_token():
    application = build_application()
    assert application.bot.token == config.LORE_BOT_TOKEN


def test_build_application_registers_no_handlers_yet():
    # Phase 8 is skeleton-only — Phase 9 registers /start, /vincular, and
    # the capture/correction conversation handlers. Until then this must
    # stay inert: no handler groups attached.
    application = build_application()
    assert application.handlers == {}
