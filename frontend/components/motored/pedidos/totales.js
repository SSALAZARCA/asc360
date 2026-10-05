/** The three totals of a whole corrida (detail boxes and list columns): labels, help texts and formatted figures. */
import { formatCOP } from '../../../lib/motored/formatCOP';
import { unidades } from './formato';

export const AYUDA_VALOR = 'Valor total: la suma en pesos de lo que se va a pedir en todas las tiendas (cantidad a pedir por precio), igual a la suma de los valores que muestra la pestaña Tiendas. Las referencias sin precio no suman al valor.';
export const AYUDA_REFERENCIAS = 'Referencias: cuántas referencias distintas se piden en la corrida (con cantidad mayor a cero en alguna tienda). Una referencia pedida en varias tiendas cuenta una sola vez.';
export const AYUDA_UNIDADES = 'Unidades: la suma de las unidades a pedir de todas las tiendas, igual a la suma de las unidades que muestra la pestaña Tiendas.';

/** `[{ clave, label, valor, ayuda }]` of a corrida's `totales_corrida`; every figure is `—` while there are none. */
export function cifrasTotales(totales) {
  const t = totales || {};
  return [
    { clave: 'valor', label: 'Valor total', valor: formatCOP(t.valor_total), ayuda: AYUDA_VALOR },
    { clave: 'referencias', label: 'Referencias', valor: unidades(t.referencias), ayuda: AYUDA_REFERENCIAS },
    { clave: 'unidades', label: 'Unidades', valor: unidades(t.unidades), ayuda: AYUDA_UNIDADES },
  ];
}
