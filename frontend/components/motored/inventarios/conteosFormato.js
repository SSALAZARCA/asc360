/**
 * Shared labels, permissions and number formats of the inventory counts
 * screens (odd/motored-conteos-inventario, WU11/WU12). UX only: the backend
 * enforces every role rule.
 */
import { getRolActual } from '../../../lib/motored/motoredFetch';
import { ROLES_LIDER_CONTEO } from '../../../lib/motored/session';

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

/**
 * Readable name of each role that may be assigned as leader (the schedule
 * dialog's leader select). ADMIN may be assigned but is not scoped: it is
 * deliberately absent from ROLES_LIDER_CONTEO / esLiderDeConteo.
 */
export const NOMBRE_ROL_LIDER = {
  LIDER_INVENTARIOS: 'Líder de inventarios',
  COORDINADOR_REPUESTOS: 'Coordinador de repuestos',
  ADMIN: 'Administrador',
};

/** Whether a role leads counts: LIDER_INVENTARIOS or COORDINADOR_REPUESTOS. */
export function esLiderDeConteo(rol) {
  return ROLES_LIDER_CONTEO.includes(rol);
}

/** What the signed-in role may do: ADMIN everything, a leader operates, GERENCIA reads. */
export function permisosConteo(role = getRolActual()) {
  return {
    role,
    administra: role === 'ADMIN',
    opera: role === 'ADMIN' || esLiderDeConteo(role),
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

/** The pair's latest sign of life: its last reading or its last request, whichever is newer. */
export function ultimaSenal(sesion) {
  const marcas = [sesion.ultima_lectura_en, sesion.ultima_actividad_en].filter(Boolean);
  if (marcas.length === 0) return sesion.conectada_en || null;
  return marcas.reduce((a, b) => (new Date(a) >= new Date(b) ? a : b));
}

/** Whole minutes since the pair's last reading or activity, or null when it is active (or not connected). */
export function minutosSinActividad(sesion, ahora = Date.now()) {
  if (sesion.estado !== 'CONECTADA') return null;
  const desde = ultimaSenal(sesion);
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

/** Counted referencias as a rounded whole percentage of the universe; 100 only when all are counted (null without a universe). */
export function porcentajeAvance(progreso) {
  if (!progreso || !progreso.refs_universo) return null;
  const pct = Math.round((100 * progreso.refs_contadas) / progreso.refs_universo);
  return pct === 100 && progreso.refs_contadas < progreso.refs_universo ? 99 : pct;
}

/** Units inside the system as a rounded whole percentage of the system's units; 100 only when all are in (null without system units). */
export function porcentajeUnidades(unidades) {
  const sistema = Number(unidades?.sistema_total);
  if (!unidades || !Number.isFinite(sistema) || sistema <= 0) return null;
  const dentro = Number(unidades.dentro_esperado) || 0;
  const pct = Math.round((100 * dentro) / sistema);
  return pct === 100 && dentro < sistema ? 99 : pct;
}

/** "39 unidades" / "1 unidad" (quantities may carry decimals). */
export function formatUnidades(valor) {
  const n = Number(valor) || 0;
  return `${formatCantidad(n)} ${n === 1 ? 'unidad' : 'unidades'}`;
}

/** The pairs of `/sesiones` with the panel's readings count, units and last reading (matched by `sesion_id`). */
export function unirParejas(sesiones, parejas) {
  const porId = new Map((parejas || []).map((p) => [p.sesion_id, p]));
  return sesiones.map((s) => {
    const p = porId.get(s.id);
    return p ? { ...s, lecturas: p.lecturas, unidades: p.unidades, ultima_lectura_en: p.ultima_lectura_en } : s;
  });
}
