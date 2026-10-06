/**
 * Every date-time Motored shows is in Colombia time (America/Bogota, UTC-5, no DST),
 * whatever the browser's time zone. The API sends instants in UTC with an offset, but
 * an ISO string without `Z`/offset is still read as UTC (never as the browser's local
 * time), so a naive value cannot show the wrong hour. A date-only `YYYY-MM-DD` is a
 * calendar date and is never shifted.
 */
const ZONA = 'America/Bogota';
const VACIO = '—';
const SOLO_FECHA = /^\d{4}-\d{2}-\d{2}$/;
const TIENE_ZONA = /(Z|[+-]\d{2}(:?\d{2})?)$/i;

const formato = new Intl.DateTimeFormat('es-CO', {
  timeZone: ZONA, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
});

const esSoloFecha = (valor) => typeof valor === 'string' && SOLO_FECHA.test(valor.trim());

/** A `Date` for an instant (Date or ISO string); `null` when empty or invalid. */
export function parseInstante(valor) {
  if (valor === null || valor === undefined || valor === '') return null;
  if (valor instanceof Date) return Number.isNaN(valor.getTime()) ? null : valor;
  if (typeof valor !== 'string') return null;
  const texto = valor.trim();
  if (SOLO_FECHA.test(texto)) {
    const [anio, mes, dia] = texto.split('-').map(Number);
    // Noon UTC is 07:00 in Bogota: the same calendar day on both sides.
    const fecha = new Date(Date.UTC(anio, mes - 1, dia, 12));
    return Number.isNaN(fecha.getTime()) ? null : fecha;
  }
  const iso = texto.replace(' ', 'T');
  const horaParte = iso.split('T')[1] || '';
  const fecha = new Date(TIENE_ZONA.test(horaParte) ? iso : `${iso}Z`);
  return Number.isNaN(fecha.getTime()) ? null : fecha;
}

const partes = (fecha) => Object.fromEntries(formato.formatToParts(fecha).map((p) => [p.type, p.value]));

/** `05/10/2026` (a date-only value is returned as is). */
export function fechaBogota(valor) {
  if (esSoloFecha(valor)) {
    const [anio, mes, dia] = valor.trim().split('-');
    return `${dia}/${mes}/${anio}`;
  }
  const fecha = parseInstante(valor);
  if (!fecha) return VACIO;
  const p = partes(fecha);
  return `${p.day}/${p.month}/${p.year}`;
}

/** `07:43`. */
export function horaBogota(valor) {
  const fecha = parseInstante(valor);
  if (!fecha || esSoloFecha(valor)) return VACIO;
  const p = partes(fecha);
  return `${p.hour}:${p.minute}`;
}

/** `05/10/2026 07:43` (a date-only value shows just the date). */
export function fechaHoraBogota(valor) {
  if (esSoloFecha(valor)) return fechaBogota(valor);
  const fecha = parseInstante(valor);
  if (!fecha) return VACIO;
  const p = partes(fecha);
  return `${p.day}/${p.month}/${p.year} ${p.hour}:${p.minute}`;
}
