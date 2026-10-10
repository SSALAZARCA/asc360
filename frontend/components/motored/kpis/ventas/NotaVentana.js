import { COLOR } from '../tokens';

export const TEXTO_VENTANA = 'Últimos 12 meses · no cambia con el período';
const TIP = 'Esta gráfica siempre muestra los últimos 12 meses con venta, sin importar el período elegido. El filtro de tiendas y de HMCL sí se aplica.';

/** Muted line under the title of the charts that do not follow the Período filter. */
export default function NotaVentana() {
  return <p title={TIP} style={{ margin: '4px 0 0', fontSize: 11.5, color: COLOR.muted }}>{TEXTO_VENTANA}</p>;
}
