// Pure helpers: the KPI cards and the "Por tienda" rows are derived from the detalle items the filters leave in.

/** Keeps the items that pass the Tienda, Estado and Antigüedad filters (age limits inclusive, null = open). */
export function filtrarItems(items, { sucursal, estado, edad }) {
  return items.filter((i) => (
    (!sucursal || i.sucursal_id === sucursal)
    && (!estado || i.estado === estado)
    && (edad?.min == null || i.dias >= edad.min)
    && (edad?.max == null || i.dias <= edad.max)));
}

/** Same shape as the API summary: counters per state, oldest age and total value. */
export function resumir(items) {
  const cuenta = (e) => items.filter((i) => i.estado === e).length;
  return {
    pendientes: items.length,
    llegaron_sin_ingresar: cuenta('LLEGO'),
    sin_confirmar: cuenta('SIN_CONFIRMAR'),
    aun_no_llegan: cuenta('NO_HA_LLEGADO'),
    mas_antigua: items.length ? Math.max(...items.map((i) => Number(i.dias) || 0)) : null,
    valor_pendiente: items.reduce((suma, i) => suma + (Number(i.valor) || 0), 0),
  };
}

/** One summary row per store present in the items. */
export function agruparPorTienda(items) {
  const grupos = new Map();
  items.forEach((i) => {
    if (!grupos.has(i.sucursal_id)) grupos.set(i.sucursal_id, { tienda: i.tienda, lista: [] });
    grupos.get(i.sucursal_id).lista.push(i);
  });
  return [...grupos].map(([sucursal_id, { tienda, lista }]) => ({ sucursal_id, tienda, ...resumir(lista) }));
}

/** Distinct stores of the items, by name, for the Tienda select. */
export function tiendasDe(items) {
  const mapa = new Map();
  items.forEach((i) => mapa.set(i.sucursal_id, i.tienda));
  return [...mapa].map(([sucursal_id, tienda]) => ({ sucursal_id, tienda }))
    .sort((a, b) => String(a.tienda).localeCompare(String(b.tienda), 'es'));
}
