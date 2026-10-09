/**
 * frontend/lib/motored/permisosPorRol.js
 *
 * Source of the read-only "Roles y permisos" matrix (Usuarios). It owns no
 * permission of its own where one already exists: each screen reads the sidebar
 * entry, the page gate constant or the Maestros tab rule that really decides
 * access. Only rules enforced solely by the backend (Telegram) live here, noted
 * in `nota`. `motored-roles-permisos.test.jsx` fails when this drifts from the
 * sidebar, the gates or the layout roles. UX only: the backend is the real
 * enforcement.
 */
import { menuItemsFor } from '../../components/motored/MotoredSidebar';
import { PEDIDOS_ROLES } from './usePedidosGate';
import { TABLERO_ROLES } from '../../components/motored/tablero-asesores/useTableroGate';
import { CONFIGURACION_ROLES } from '../../components/motored/configuracion/useConfiguracionGate';
import { DETRACTORES_ROLES } from './useDetractoresGate';
import { filtrarTabsPorRol, PRESUPUESTOS_ROLES } from './maestrosTabsPorRol';
import { GESTION_REPUESTOS_ROLES } from './session';

/** Web roles (ASESOR_MOSTRADOR has no web access: it only talks to the Telegram bot). */
export const ROLES = [
  { id: 'ADMIN', ayuda: 'Administra toda la aplicación.' },
  { id: 'COMPRAS', ayuda: "Gestiona pedidos de repuestos y ve los KPI's." },
  { id: 'GERENCIA', ayuda: "Ve Presupuestos y KPI's" },
  { id: 'SUCURSAL', ayuda: 'Sin pantallas habilitadas por ahora: solo cambia su contraseña.' },
  { id: 'CONSULTA', ayuda: 'Sin pantallas habilitadas por ahora: solo cambia su contraseña.' },
  { id: 'SERVICIO_CLIENTE', ayuda: 'Atiende la encuesta de satisfacción y los detractores.' },
  { id: 'COORDINADOR_REPUESTOS', ayuda: "Ve los KPI's y confirma los ingresos de facturas de pedidos." },
  { id: 'LIDER_INVENTARIOS', ayuda: 'Dirige los conteos de inventario que le asignan.' },
];

// Backend-only rule: `_require_telegram_propio` in api/usuarios.py.
const TELEGRAM_ROLES = ['ADMIN', 'COMPRAS'];

const enSidebar = (id, rol) => menuItemsFor({ role: rol })
  .flatMap((item) => item.children || [item])
  .some((item) => item.id === id);
const enMaestros = (tab, rol) => enSidebar('maestros', rol) && filtrarTabsPorRol([tab], rol).length > 0;

export const PANTALLAS = [
  { id: 'inicio', nombre: 'Inicio', sidebarId: 'inicio', nota: 'Resumen del día de cada rol.', visible: (rol) => enSidebar('inicio', rol) },
  { id: 'maestros', nombre: 'Maestros', sidebarId: 'maestros', nota: 'GERENCIA entra solo a la pestaña Presupuestos.', visible: (rol) => enSidebar('maestros', rol) },
  { id: 'maestros-datos', nombre: 'Maestros: datos y catálogos', nota: 'Sucursales, proveedores, referencias, clientes y vendedores.', visible: (rol) => enMaestros({}, rol) },
  { id: 'cargas', nombre: 'Cargas de archivos', nota: 'Pestañas de movimientos dentro de Maestros.', visible: (rol) => enMaestros({}, rol) },
  { id: 'presupuestos', nombre: 'Maestros: Presupuestos', nota: 'Presupuesto mensual por asesor.', visible: (rol) => enMaestros({ roles: PRESUPUESTOS_ROLES }, rol) },
  { id: 'tablero-asesores', nombre: "KPI's", sidebarId: 'tablero-asesores', nota: '', visible: (rol) => TABLERO_ROLES.includes(rol) },
  { id: 'ingresos-facturas', nombre: 'Gestión repuestos: Ingresos facturas', sidebarId: 'ingresos-facturas', nota: 'ADMIN, COMPRAS y GERENCIA solo consultan; confirma el coordinador de repuestos.', visible: (rol) => GESTION_REPUESTOS_ROLES.includes(rol) },
  { id: 'conteos', nombre: 'Inventarios: Conteos', sidebarId: 'conteos', nota: 'En construcción: por ahora solo ADMIN la ve en el menú.', visible: (rol) => enSidebar('conteos', rol) },
  { id: 'pedidos', nombre: 'Pedidos y corridas', sidebarId: 'pedidos', nota: '', visible: (rol) => PEDIDOS_ROLES.includes(rol) },
  { id: 'topes', nombre: 'Topes de pedido', nota: 'Dentro de Pedidos.', visible: (rol) => PEDIDOS_ROLES.includes(rol) },
  { id: 'ventas-perdidas', nombre: 'Ventas perdidas', sidebarId: 'ventas-perdidas', nota: '', visible: (rol) => enSidebar('ventas-perdidas', rol) },
  { id: 'encuesta-satisfaccion', nombre: 'Encuesta satisfacción', sidebarId: 'encuesta-satisfaccion', nota: '', visible: (rol) => enSidebar('encuesta-satisfaccion', rol) },
  { id: 'detractores', nombre: 'Detractores', sidebarId: 'detractores', nota: '', visible: (rol) => DETRACTORES_ROLES.includes(rol) },
  { id: 'usuarios-gestion', nombre: 'Gestión de usuarios', sidebarId: 'usuarios-gestion', nota: '', visible: (rol) => enSidebar('usuarios-gestion', rol) },
  { id: 'roles-permisos', nombre: 'Roles y permisos', nota: 'Pestaña dentro de Usuarios.', visible: (rol) => enSidebar('usuarios-gestion', rol) },
  { id: 'ingresos', nombre: 'Registro de ingresos', sidebarId: 'ingresos', nota: '', visible: (rol) => enSidebar('ingresos', rol) },
  { id: 'configuracion', nombre: 'Configuración', sidebarId: 'configuracion', nota: '', visible: (rol) => CONFIGURACION_ROLES.includes(rol) },
  { id: 'mi-cuenta', nombre: 'Cambiar mi contraseña', sidebarId: 'mi-cuenta', nota: '', visible: (rol) => enSidebar('mi-cuenta', rol) },
  { id: 'telegram', nombre: 'Vincular Telegram', nota: 'Solo sobre la propia cuenta. Regla del servidor: la pantalla de Usuarios hoy la ofrece solo a ADMIN.', visible: (rol) => TELEGRAM_ROLES.includes(rol) },
];

export function tienePermiso(pantallaId, rol) {
  return Boolean(PANTALLAS.find((p) => p.id === pantallaId)?.visible(rol));
}
