/** Wording of the "Datos actualizados" line of the KPI's. Times are shown in Bogota (UTC-5, no DST). */
import { parseInstante } from '../../../lib/motored/fechas';

const ZONA = 'America/Bogota';

const partes = (fecha) => {
  const formato = new Intl.DateTimeFormat('es-CO', {
    timeZone: ZONA, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  });
  return Object.fromEntries(formato.formatToParts(fecha).map((p) => [p.type, p.value]));
};

/** `a las 10:30` for today, `el 02/10 a las 22:00` for another day (both in Bogota time); '' when invalid. */
export function momentoActualizacion(iso, ahora = new Date()) {
  const fecha = parseInstante(iso);
  if (!fecha) return '';
  const f = partes(fecha);
  const hoy = partes(ahora);
  const hora = `a las ${f.hour}:${f.minute}`;
  const mismoDia = f.day === hoy.day && f.month === hoy.month && f.year === hoy.year;
  return mismoDia ? hora : `el ${f.day}/${f.month} ${hora}`;
}

export function textoActualizado(iso, ahora = new Date()) {
  const momento = momentoActualizacion(iso, ahora);
  return momento ? `Datos actualizados ${momento}` : '';
}

/** What the ADMIN sees while the live queries still answer: how far the precomputed summary is. */
export function textoResumen(estado, ahora = new Date()) {
  if (!estado) return '';
  const sufijo = ' · aún no activo';
  if (estado.reconstruyendo) return `Resumen precalculado: en construcción${sufijo}`;
  if (!estado.ultima_reconstruccion_total) return `Resumen precalculado: pendiente${sufijo}`;
  if (estado.sucio) return `Resumen precalculado: pendiente de recalcular${sufijo}`;
  const momento = momentoActualizacion(estado.actualizado_en || estado.ultima_reconstruccion_total, ahora);
  return `Resumen precalculado: listo (actualizado ${momento})${sufijo}`;
}
