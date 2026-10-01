/** Header cell and state dot of ONE tienda column of the consolidated matrix. */
import { abreviarTienda } from './formato';
import { ESTADO_PEDIDO_ETIQUETA } from './EstadoPedidoBadge';
import { stickyHeadStyle, thCompactStyle } from './styles';

export const ANCHO_TIENDA = 64;

const CALCULO = { FALLIDA: 'Fallida', OMITIDA: 'Omitida' };
const COLOR = {
  BORRADOR: 'var(--motored-warning, #d97706)', CERRADO: 'var(--motored-text, #1a1a18)',
  ENVIADO: 'var(--motored-success, #15803d)', FALLIDA: 'var(--motored-danger, #c0392b)',
  OMITIDA: 'var(--motored-text-muted, #5a5a5a)',
};

export const ETIQUETA_ESTADO = { ...ESTADO_PEDIDO_ETIQUETA, ...CALCULO };

/** The state a tienda column shows: its failed calculation, else its pedido state (none for a scenario). */
export const estadoColumna = (t) => (CALCULO[t.estado] ? t.estado : t.estado_pedido);
export const etiquetaColumna = (t) => ETIQUETA_ESTADO[estadoColumna(t)] || null;
export const sinPedido = (t) => Boolean(CALCULO[t.estado]);

/** Tooltip of the header: "Nombre: Estado" or, for a tienda without calculation, "Nombre: Fallida - message (CODE)". */
export function tituloColumna(t) {
  const etiqueta = etiquetaColumna(t);
  if (!etiqueta) return t.nombre;
  if (!sinPedido(t)) return `${t.nombre}: ${etiqueta}`;
  const detalle = [t.mensaje, t.codigo && `(${t.codigo})`].filter(Boolean).join(' ');
  return `${t.nombre}: ${etiqueta}${detalle ? ` - ${detalle}` : ''}`;
}

/** The coloured dot of a state; it says the state in words (`oculto` when the text already sits next to it). */
export function PuntoEstado({ estado, oculto }) {
  const forma = { display: 'inline-block', width: '10px', height: '10px', borderRadius: '50%', background: COLOR[estado] };
  if (oculto) return <span aria-hidden="true" style={forma} />;
  return <span role="img" aria-label={ETIQUETA_ESTADO[estado]} style={forma} />;
}

export default function EncabezadoTienda({ tienda }) {
  const marca = sinPedido(tienda) ? etiquetaColumna(tienda) : null;
  return (
    <th title={tituloColumna(tienda)} style={{ ...thCompactStyle, ...stickyHeadStyle, width: `${ANCHO_TIENDA}px`, padding: '0 2px 8px', whiteSpace: 'normal', overflow: 'hidden' }}>
      {etiquetaColumna(tienda) && <PuntoEstado estado={estadoColumna(tienda)} />}
      <div style={{ fontSize: '0.7rem', fontWeight: 600, overflowWrap: 'anywhere' }}>{abreviarTienda(tienda.nombre)}</div>
      {marca && <div style={{ fontSize: '0.65rem', fontWeight: 700, color: COLOR[tienda.estado] }}>{marca}</div>}
    </th>
  );
}
