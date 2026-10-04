/** View-models of the Tecnired block of the Ventas tab. */
import { millones, pct } from '../format';
import { CATEGORIA } from '../tokens';
import { nombreLinea } from './datos';

const sumaDe = (obj, claves) => claves.reduce((t, k) => t + (obj[k] ?? 0), 0);

/** Per month: Tecnired sales, bar height (% of the largest) and its share of the month's total sales. */
export function barrasMensuales(data) {
  const meses = Object.keys(data.tecnired.por_mes).sort();
  const maximo = Math.max(1, ...meses.map((m) => data.tecnired.por_mes[m].venta));
  const ventaMes = data.total.venta.por_mes;
  return meses.map((mes) => {
    const venta = data.tecnired.por_mes[mes].venta;
    return { mes, venta, texto: millones(venta), alto: (venta / maximo) * 100, fraccion: ventaMes[mes] > 0 ? venta / ventaMes[mes] : null };
  });
}

/** Chip text with the share of sales in the first and last selected months, or null with one month. */
export function chipParticipacion(barras) {
  const [primero, ...resto] = barras.filter((b) => b.fraccion !== null);
  const ultimo = resto[resto.length - 1];
  if (!primero || !ultimo) return null;
  return { texto: `${ultimo.fraccion >= primero.fraccion ? '▲' : '▼'} ${pct(primero.fraccion)} → ${pct(ultimo.fraccion)} de la venta`, variante: ultimo.fraccion >= primero.fraccion ? 'up' : 'down' };
}

/** Repuestos / Lubricantes / Otras, as in the design. */
export function mezclaLineas(data) {
  const porLinea = data.tecnired.por_linea;
  const todas = Object.keys(porLinea);
  const resto = todas.filter((l) => l !== 'REPUESTOS' && l !== 'LUBRICANTES');
  return [
    { label: nombreLinea('REPUESTOS'), value: porLinea.REPUESTOS ?? 0, color: CATEGORIA[0] },
    { label: nombreLinea('LUBRICANTES'), value: porLinea.LUBRICANTES ?? 0, color: CATEGORIA[3] },
    { label: 'Otras', value: sumaDe(porLinea, resto), color: CATEGORIA[5] },
  ];
}
