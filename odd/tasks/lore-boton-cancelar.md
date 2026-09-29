# Lore bot: Cancel button on every step

## Objective
Users can abort any Lore conversation (Registro, Captura, Correccion) with a tap on a "Cancelar" button, instead of typing `/cancelar`.

## Current state (mapped 2026-09-28)
- There are 3 ConversationHandlers in `lore-bot/lore/main.py`: Registro (:48), Captura (:71) and Correccion (:126). Each has a single fallback, `CommandHandler("cancelar")`, handled by `registro.py:317`, `captura.py:839` and `correccion.py:324`. All three call `update.message.reply_text`, so they would crash on a callback update.
- Inline cancel buttons exist only on the final confirm steps: `lore_reg_cancelar`, `lore_cap_cancelar` and `lore_cor_anular_cancelar`.
- These states take free text: Registro NOMBRE/CELULAR, Captura MANUAL/CANTIDAD and Correccion CANTIDAD. Captura FOTO takes a photo or text.
- `callback_huerfano` (`^lore_`, main.py:193) catches any `lore_*` callback that no state claims.

## Decision
- Use an INLINE "✖️ Cancelar" button, not a reply-keyboard button. In the free-text states, a reply-keyboard "Cancelar" would be read as a name, code or quantity.
- Every prompt message sent inside the 3 conversations carries the button. In steps that already have an inline keyboard, it is appended as the last row. In text and photo steps, it is attached as the message's only inline keyboard.
- There is one shared callback_data, `lore_cancelar`, handled as a FALLBACK in all 3 conversations with the pattern `^lore_cancelar$`, so it works from any state. It must not collide with the existing `lore_*_cancelar` / `lore_cor_anular_*` patterns or be swallowed by `callback_huerfano`.
- The cancel handlers work for both the command and the callback: they answer the callback query, remove the buttons from the tapped message where practical, clear the conversation's user_data draft exactly as `/cancelar` does today, and end the conversation. `/cancelar` keeps working.
- The existing final-step cancel buttons keep working. Unify them with the new callback only if that is trivially safe.

## TDD
- Mode: strict.
- Runner: `lore-bot`'s pytest. Find the venv or command the repo uses; `asyncio_mode = auto`.

## Tasks
- [x] **T1: shared helper.** The Cancelar button, its row, and a function that appends it to an inline keyboard. Also make the cancel handlers callback-safe. Tests. Route: delegated writer.
- [x] **T2: wire the button** into every prompt of the 3 conversations, and register the `^lore_cancelar$` fallback in main.py. Tests via `test_main.py` dispatch: a cancel tap from a free-text state, from an inline state, and from FOTO ends the conversation and clears the draft. Route: same writer.
- [x] **T1b: retry messages keep their buttons.** `captura.confirmar` on `BackendCaido`/unmapped `LoreApiError` edited the message to "Tocá Confirmar de nuevo" without `reply_markup`, so Telegram dropped the keyboard and the user was stuck in CONFIRMAR. Same bug in `correccion.resolver_confirmacion_anular`'s retry branches. Fix: shared `_teclado_confirmacion()` / `_teclado_confirmar_anular(carga_id)` builders reused on the retry edit (one cancel control each, see T1d).
- [x] **T1c: global /cancelar.** With no active conversation, `/cancelar` (and the `/cancela` typo) got no reply, and a stray `lore_cancelar` tap fell into the "sesión expirada" orphan path. Fix: `_common.nada_para_cancelar` ("No hay nada para cancelar.") registered in main.py after the 3 conversations and before `callback_huerfano`, for both the commands and `^lore_cancelar$`.
- [x] **T1d: one cancel control per message.** Registro and Captura confirm steps keep only their own "❌ Cancelar" (next to ✅ Confirmar); the ✖️ row is not added there. Correccion CONFIRMAR_ANULAR: "❌ No" (`lore_cor_anular_cancelar`) clears the state and ends the conversation, the same as cancel, so the ✖️ row is dropped there too. Old callbacks unchanged.
- [x] **T1e: repeated retry edits.** A second failure in a row re-edited the retry message to identical text and buttons, and Telegram raised an uncaught `BadRequest("Message is not modified")`. Fix: `_common.editar_o_ignorar_sin_cambios` treats only that BadRequest as a no-op (others re-raise), used in `captura.confirmar` (both retry branches) and `correccion.resolver_confirmacion_anular` (retry branch). Every other same-state edit either changes content or was already guarded (`alternar_seleccion`, `descartar_no_resuelta`).
- [x] **T3: commit and push to main.** Repo policy. Parent spot check: `lore-bot/.venv/bin/python -m pytest -q` returned 326 passed.

## Progress
- 2026-09-28: document created from the read-only map.
- 2026-09-28: T1, T1b, T1c, T2 implemented with strict TDD (RED observed before each GREEN). Baseline `lore-bot/.venv/bin/python -m pytest -q`: 273 passed. Final, same command: 320 passed (47 new tests). Not committed (T3 pending).
- 2026-09-28: T1d and T1e implemented with strict TDD (RED observed: 7 failures for T1d, 2 failures plus 1 import error for T1e). `lore-bot/.venv/bin/python -m pytest -q`: 326 passed. Not committed (T3 pending). Out of scope, tracked separately: leftover saved data when some Captura/Correccion handlers end on a bad id.
