/**
 * Shared labels, permissions and number formats of the inventory counts
 * screens (odd/motored-conteos-inventario, WU11/WU12). UX only: the backend
 * enforces every role rule.
 */
import { getRolActual } from '../../../lib/motored/motoredFetch';

export const ESTADOS_CONTEO = [
  { value: 'PROGRAMADO', label: 'Programado' },
  { value: 'EN_CONTEO', label: 'En conteo' },
  { value: 'EN_RECONTEO', label: 'En reconteo' },
  { value: 'CERRADO', label: 'Cerrado' },
  { value: 'ANULADO', label: 'Anulado' },
];
export const ESTADOS_ABIERTOS = ['EN_CONTEO', 'EN_RECONTEO'];

export function labelEstado(estado) {
  return ESTADOS_CONTEO.find((e) => e.value === estado)?.label ?? estado;
}

/** What the signed-in role may do: ADMIN everything, the leader operates, GERENCIA reads. */
export function permisosConteo(role = getRolActual()) {
  return {
    role,
    administra: role === 'ADMIN',
    opera: role === 'ADMIN' || role === 'LIDER_INVENTARIOS',
  };
}

const ENTERO = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 0 });
const DECIMAL = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 1 });
const PESOS = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 0 });

export function formatEntero(valor) {
  const n = Number(valor);
  return valor == null || !Number.isFinite(n) ? '—' : ENTERO.format(n);
}

/** Quantities come as Decimal strings; show up to one decimal. */
export function formatCantidad(valor) {
  const n = Number(valor);
  return valor == null || !Number.isFinite(n) ? '—' : DECIMAL.format(n);
}

/** "−$1.320.000" / "+$182.000", the prototype's signed money. */
export function formatPesosConSigno(valor) {
  const n = Number(valor);
  if (valor == null || !Number.isFinite(n)) return '—';
  const signo = n < 0 ? '−' : n > 0 ? '+' : '';
  return `${signo}$${PESOS.format(Math.abs(n))}`;
}

export function formatPesos(valor) {
  const n = Number(valor);
  return valor == null || !Number.isFinite(n) ? '—' : `$${PESOS.format(n)}`;
}

export function formatPorcentaje(valor) {
  const n = Number(valor);
  return valor == null || !Number.isFinite(n) ? '—' : `${DECIMAL.format(n)} %`;
}

/** "482 913": the prototype's grouped code. */
export function formatCodigo(codigo) {
  return codigo ? `${codigo.slice(0, 3)} ${codigo.slice(3)}` : '';
}

/** "hace 8 s" / "hace 3 min" / "hace 2 h" from an ISO instant. */
export function haceCuanto(instante, ahora = Date.now()) {
  if (!instante) return 'sin actividad';
  const segundos = Math.max(0, Math.round((ahora - new Date(instante).getTime()) / 1000));
  if (segundos < 60) return `hace ${segundos} s`;
  if (segundos < 3600) return `hace ${Math.floor(segundos / 60)} min`;
  return `hace ${Math.floor(segundos / 3600)} h`;
}

/** A connected pair silent for longer than this may hold readings it has not sent (owner rule, WU12). */
export const MINUTOS_SIN_ACTIVIDAD = 2;

/** Whole minutes since the pair's last activity, or null when it is active (or not connected). */
export function minutosSinActividad(sesion, ahora = Date.now()) {
  if (sesion.estado !== 'CONECTADA') return null;
  const desde = sesion.ultima_actividad_en || sesion.conectada_en;
  if (!desde) return null;
  const minutos = (ahora - new Date(desde).getTime()) / 60000;
  return minutos > MINUTOS_SIN_ACTIVIDAD ? Math.floor(minutos) : null;
}

/** The connected pairs silent for too long: [{ sesion, minutos }]. */
export function parejasSinActividad(sesiones, ahora = Date.now()) {
  return sesiones
    .map((sesion) => ({ sesion, minutos: minutosSinActividad(sesion, ahora) }))
    .filter((p) => p.minutos != null);
}

/** The pair label without its members: "Pareja 3 · Sofía L. y Diego M." -> "Pareja 3". */
export function parejaCorta(etiqueta) {
  return (etiqueta || '').split(' · ')[0];
}
