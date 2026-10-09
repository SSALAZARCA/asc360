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

const BASE_TRASLADOS = '/gestion-repuestos/traslados';

/**
 * Pending transfers: `{ ultima_carga, items }`, oldest first; filters `{ sucursal, estado, min_dias, max_dias }`.
 * An item is `{ documento, bodega_salida, sale, sucursal_id, llega, tienda, fecha, dias, refs, unidades, num_lineas,
 * lineas: [{ referencia, descripcion, cantidad }], estado: 'SIN_CONFIRMAR' | 'RECIBIDO' | 'NO_HA_LLEGADO', aviso_erp,
 * confirmado_por, confirmado_en }`; `sucursal_id` is the RECEIVING store.
 */
export const getTrasladosDetalle = (filtros) => motoredFetchJson(`${BASE_TRASLADOS}/detalle${consulta(filtros)}`);

/** `{ historial: [{ estado, por, canal, en }] }`, newest first. A transfer is identified by (documento, bodega_salida). */
export const getTrasladosHistorial = (documento, bodegaSalida) => (
  motoredFetchJson(`${BASE_TRASLADOS}/historial${consulta({ documento, bodega_salida: bodegaSalida })}`)
);

/** The asesor card block of one receiving store: `{ ultima_carga, items, resumen }` (403 for a role that cannot read it). */
export const getTrasladosAsesor = (sucursal) => motoredFetchJson(`${BASE_TRASLADOS}/asesor${consulta({ sucursal })}`);

/** ADMIN, COORDINADOR_REPUESTOS and ANALISTA_ADMINISTRATIVO: `{ documento, bodega_salida, estado: 'RECIBIDO' | 'NO_HA_LLEGADO' }`; resolves the updated item. */
export const confirmarTraslado = (cuerpo) => (
  motoredFetchJson(`${BASE_TRASLADOS}/confirmar`, { method: 'POST', body: JSON.stringify(cuerpo) })
);
