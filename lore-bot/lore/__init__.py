"""Lore — Telegram bot for Motored's lost-sale (demanda perdida) capture.

Standalone service, independent from Sonia (the unrelated UM product's own
Telegram bot, in the sibling directory one level up): no shared code,
imports, database, tokens, or secrets. See `tests/test_isolation.py` for
the automated check.
"""
