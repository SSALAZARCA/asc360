/** Sugerido versus a pedir (units and value) of one tienda pedido. */
import InfoTooltip from '../InfoTooltip';
import { formatCOP } from '../../../lib/motored/formatCOP';
import { unidades } from './formato';
import { cardStyle, mutedStyle, numStyle } from './styles';

const SUGERIDO_TEXTO = 'Sugerido: lo que calculó el motor. No cambia aunque el comprador ajuste cantidades.';
const PEDIR_TEXTO = 'Cantidad a pedir: lo que se va a mandar a HMCL. Parte igual al sugerido y refleja los ajustes del comprador.';

function Bloque({ titulo, ayuda, uds, valor }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', ...numStyle }}>
      <span style={{ ...mutedStyle, display: 'inline-flex', alignItems: 'center' }}>{titulo}<InfoTooltip text={ayuda} /></span>
      <span style={{ fontSize: '1.1rem', fontWeight: 700 }}>{`${unidades(uds)} uds`}</span>
      <span style={mutedStyle}>{formatCOP(valor)}</span>
    </div>
  );
}

export default function TotalesPedido({ totales }) {
  return (
    <section style={{ ...cardStyle, flexDirection: 'row', flexWrap: 'wrap', gap: '2rem', alignItems: 'center' }}>
      <h2 style={{ margin: 0, fontSize: '0.8rem' }}>Totales</h2>
      <Bloque titulo="Sugerido" ayuda={SUGERIDO_TEXTO} uds={totales.unidades_sugerido} valor={totales.valor_sugerido} />
      <Bloque titulo="A pedir" ayuda={PEDIR_TEXTO} uds={totales.unidades_a_pedir} valor={totales.valor_a_pedir} />
    </section>
  );
}
