/** Pure rules of the scenario comparison: network totals and the wording of the class and the real pedido. */
import { unidades } from './formato';

const CAMPOS = [
  ['unidadesReal', 'unidades_real'], ['unidadesPrueba', 'unidades_prueba'], ['diferenciaUnidades', 'diferencia_unidades'],
  ['valorReal', 'valor_real'], ['valorPrueba', 'valor_prueba'], ['diferenciaValor', 'diferencia_valor'],
];

/** The totals of every compared tienda added up: units and value on both sides and their differences. */
export function sumarTotales(totales) {
  return Object.fromEntries(CAMPOS.map(([destino, origen]) => [
    destino, totales.reduce((suma, t) => suma + Number(t[origen]), 0),
  ]));
}

/** The class of the reference: once when both sides agree, `real → prueba` when the scenario changes it. */
export function claseTexto({ clase_real: real, clase_prueba: prueba }) {
  return real === prueba ? (real || '—') : `${real || '—'} → ${prueba || '—'}`;
}

/** `Pedido real: N` when Compras adjusted the real pedido away from the suggestion; null otherwise. */
export function pedidoRealTexto(fila) {
  if (Number(fila.pedido_final_real) === Number(fila.sugerido_real)) return null;
  return `Pedido real: ${unidades(fila.pedido_final_real)}`;
}
