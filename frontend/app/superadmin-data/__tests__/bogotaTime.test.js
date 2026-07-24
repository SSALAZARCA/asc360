/**
 * Tests for the UTC <-> Bogotá (Colombia, fixed UTC-5, no DST) datetime
 * conversion used by the Orden tab's <input type="datetime-local"> fields.
 *
 * The backend always stores/returns naive UTC ISO strings (matching
 * `datetime.utcnow()` elsewhere in this codebase). The rest of the app
 * (e.g. services/page.js's `fmtDate`) converts to Bogotá time for display
 * using `Intl`/`timeZone`, but that's read-only formatting — an editable
 * `datetime-local` input needs a real two-way conversion, and the browser's
 * own system timezone must never affect the result (a superadmin could be
 * anywhere), so this uses plain UTC-based arithmetic throughout.
 */
import { utcIsoToBogotaInputValue, bogotaInputValueToUtcIso } from '../bogotaTime';

describe('utcIsoToBogotaInputValue', () => {
  it('shifts a UTC ISO string back 5 hours to Bogotá wall-clock time', () => {
    // 22:41 UTC -> 17:41 Bogotá (UTC-5), same calendar day
    expect(utcIsoToBogotaInputValue('2026-06-30T22:41:53.061735')).toBe('2026-06-30T17:41');
  });

  it('rolls the calendar day back when the UTC time is within 5 hours of midnight', () => {
    // 02:00 UTC on the 1st -> 21:00 Bogotá on the previous day
    expect(utcIsoToBogotaInputValue('2026-07-01T02:00:00')).toBe('2026-06-30T21:00');
  });

  it('treats a string already ending in Z the same as a naive one', () => {
    expect(utcIsoToBogotaInputValue('2026-06-30T22:41:53.061735Z')).toBe('2026-06-30T17:41');
  });

  it('returns an empty string for null/empty input', () => {
    expect(utcIsoToBogotaInputValue(null)).toBe('');
    expect(utcIsoToBogotaInputValue('')).toBe('');
  });
});

describe('bogotaInputValueToUtcIso', () => {
  it('shifts a Bogotá wall-clock value forward 5 hours to UTC', () => {
    expect(bogotaInputValueToUtcIso('2026-06-30T17:41')).toBe('2026-06-30T22:41:00.000Z');
  });

  it('rolls the calendar day forward when the Bogotá time is within 5 hours of midnight', () => {
    expect(bogotaInputValueToUtcIso('2026-06-30T21:00')).toBe('2026-07-01T02:00:00.000Z');
  });

  it('returns null for an empty value', () => {
    expect(bogotaInputValueToUtcIso('')).toBeNull();
    expect(bogotaInputValueToUtcIso(null)).toBeNull();
  });
});

describe('round-trip', () => {
  it('converting UTC -> Bogotá -> UTC returns the original instant (to the minute)', () => {
    const originalUtc = '2026-06-30T22:41:00.000Z';
    const bogota = utcIsoToBogotaInputValue(originalUtc);
    const backToUtc = bogotaInputValueToUtcIso(bogota);
    expect(backToUtc).toBe(originalUtc);
  });
});
