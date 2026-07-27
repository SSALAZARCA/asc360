/**
 * UTC <-> Bogotá (Colombia) datetime conversion for <input type="datetime-local">
 * fields anywhere in the app.
 *
 * The backend stores/returns naive UTC ISO strings (matches
 * `datetime.utcnow()` elsewhere in this codebase). Colombia is a fixed
 * UTC-5 offset with no daylight saving time, so this uses plain arithmetic
 * on UTC-based Date methods throughout — the browser's own system timezone
 * never enters into it (a superadmin's session could be anywhere).
 *
 * Canonical location (moved from `app/superadmin-data/bogotaTime.js`, which
 * is now a re-export shim so its existing consumer and test keep working
 * unmodified).
 */
const BOGOTA_OFFSET_MS = 5 * 60 * 60 * 1000;

function pad2(n) {
  return String(n).padStart(2, '0');
}

// Backend ISO (naive UTC) -> "YYYY-MM-DDTHH:mm" for a datetime-local input,
// representing the same instant in Bogotá wall-clock time.
export function utcIsoToBogotaInputValue(iso) {
  if (!iso) return '';
  const asUtc = new Date(iso.endsWith('Z') ? iso : `${iso}Z`);
  const shifted = new Date(asUtc.getTime() - BOGOTA_OFFSET_MS);
  return `${shifted.getUTCFullYear()}-${pad2(shifted.getUTCMonth() + 1)}-${pad2(shifted.getUTCDate())}` +
    `T${pad2(shifted.getUTCHours())}:${pad2(shifted.getUTCMinutes())}`;
}

// datetime-local value ("YYYY-MM-DDTHH:mm", Bogotá wall-clock) -> UTC ISO
// string for the backend, WITHOUT a trailing 'Z'/offset.
//
// The backend stores/parses NAIVE datetimes everywhere (datetime.utcnow(),
// no tzinfo). `.toISOString()` always appends 'Z', which Pydantic parses
// into a timezone-AWARE datetime -- mixing that with the naive values
// already in the same DateTime column crashes asyncpg the moment it tries
// to persist it (confirmed live in production: "TypeError: can't subtract
// offset-naive and offset-aware datetimes"). Format manually instead, the
// same way `utcIsoToBogotaInputValue` does, to keep the string naive.
export function bogotaInputValueToUtcIso(value) {
  if (!value) return null;
  const [datePart, timePart] = value.split('T');
  const [year, month, day] = datePart.split('-').map(Number);
  const [hour, minute] = (timePart || '00:00').split(':').map(Number);
  const asIfUtc = Date.UTC(year, month - 1, day, hour, minute);
  const trueUtc = new Date(asIfUtc + BOGOTA_OFFSET_MS);
  return `${trueUtc.getUTCFullYear()}-${pad2(trueUtc.getUTCMonth() + 1)}-${pad2(trueUtc.getUTCDate())}` +
    `T${pad2(trueUtc.getUTCHours())}:${pad2(trueUtc.getUTCMinutes())}:00`;
}
