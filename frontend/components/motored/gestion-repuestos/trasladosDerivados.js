// Pure helpers of the Traslados screen: the cards and the "Por tienda" rows are derived from the detalle items the
// filters leave in (filtrarItems and tiendasDe are shared with the invoices screen: same sucursal_id / estado / dias).

/** Same shape as the API summary: counters per state, lines, and the oldest transfer. */
export function resumirTraslados(items) {
  const cuenta = (e) => items.filter((i) => i.estado === e).length;
  const masAntiguo = items.reduce((m, i) => (m === null || Number(i.dias) > Number(m.dias) ? i : m), null);
  return {
    pendientes: items.length,
    recibidos_sin_erp: cuenta('RECIBIDO'),
    sin_confirmar: cuenta('SIN_CONFIRMAR'),
    aun_no_llegan: cuenta('NO_HA_LLEGADO'),
    lineas: items.reduce((suma, i) => suma + (Number(i.num_lineas) || 0), 0),
    unidades: items.reduce((suma, i) => suma + (Number(i.unidades) || 0), 0),
    mas_antiguo: masAntiguo && { documento: masAntiguo.documento, tienda: masAntiguo.tienda, dias: Number(masAntiguo.dias) || 0 },
  };
}

/** One summary row per receiving store present in the items. */
export function agruparTrasladosPorTienda(items) {
  const grupos = new Map();
  items.forEach((i) => {
    if (!grupos.has(i.sucursal_id)) grupos.set(i.sucursal_id, { tienda: i.tienda, lista: [] });
    grupos.get(i.sucursal_id).lista.push(i);
  });
  return [...grupos].map(([sucursal_id, { tienda, lista }]) => {
    const r = resumirTraslados(lista);
    return { sucursal_id, tienda, ...r, mas_antiguo_dias: r.mas_antiguo.dias };
  });
}
