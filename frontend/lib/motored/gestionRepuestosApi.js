/**
 * Client of "Gestión repuestos" (`/api/motored/gestion-repuestos`). Every
 * function rejects with an `Error` that carries `status` (`motoredFetchJson`).
 * Invoices are named `RH 482915`; the stores are principal store ids.
 */
import { motoredFetchJson } from './motoredFetch';
import { descargarArchivo } from './descargas';

const BASE = '/gestion-repuestos/ingresos-facturas';

function consulta(params) {
  const q = new URLSearchParams();
  Object.entries(params || {}).forEach(([clave, valor]) => {
    if (valor !== undefined && valor !== null && valor !== '') q.set(clave, String(valor));
  });
  const texto = q.toString();
  return texto ? `?${texto}` : '';
}

/** `{ verificable_desde, resumen: { pendientes, llegaron_sin_ingresar, sin_confirmar, aun_no_llegan, mas_antigua, valor_pendiente } }`. */
export const getIngresosResumen = () => motoredFetchJson(BASE);

/** `{ verificable_desde, tiendas: [{ sucursal_id, tienda, ...resumen }] }`. */
export const getIngresosPorTienda = () => motoredFetchJson(`${BASE}/por-tienda`);

/** `{ verificable_desde, items }`, oldest first; filters `{ sucursal, estado, min_dias, max_dias }` (both limits inclusive). */
export const getIngresosDetalle = (filtros) => motoredFetchJson(`${BASE}/detalle${consulta(filtros)}`);

/** `{ historial: [{ estado, por, canal, en }] }`, newest first. */
export const getIngresosHistorial = (factura, sucursal) => (
  motoredFetchJson(`${BASE}/historial${consulta({ factura, sucursal })}`)
);

/** The asesor card block of one store: `{ verificable_desde, items, resumen }` (403 for a role that cannot read it). */
export const getIngresosAsesor = (sucursal) => motoredFetchJson(`${BASE}/asesor${consulta({ sucursal })}`);

/** ADMIN, COORDINADOR_REPUESTOS and ANALISTA_ADMINISTRATIVO: `{ factura, sucursal_id, estado: 'LLEGO' | 'NO_HA_LLEGADO' }`; resolves the updated item. */
export const confirmarIngreso = (cuerpo) => (
  motoredFetchJson(`${BASE}/confirmar`, { method: 'POST', body: JSON.stringify(cuerpo) })
);

/**
 * ADMIN and ANALISTA_ADMINISTRATIVO: downloads the ERP "Entradas x Compra" Excel of an analista
 * invoice already confirmed "LLEGO". Rejects with the backend's Spanish `detail` (404/409/422).
 */
export const descargarPlantillaIngreso = (factura, sucursal) => descargarArchivo(
  `${BASE}/plantilla${consulta({ factura, sucursal })}`,
  `Entrada_compra_${String(factura).replace(/\s+/g, '')}.xlsx`,
);
