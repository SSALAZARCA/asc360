'use client';
/** Tiendas of one corrida (read-only). Scrolls inside its box; first column and header stay in view. */
import InfoTooltip from '../InfoTooltip';
import MotoredTableScroll from '../MotoredTableScroll';
import TiendaFila from './TiendaFila';
import { ESTADO_PEDIDO_TEXTO } from './EstadoPedidoBadge';
import { stickyColStyle, stickyHeadStyle, tablaStyle, thStyle } from './styles';

const CALCULO_TEXTO = 'Cálculo: si el motor pudo calcular la tienda (OK), falló (Fallida) o se omitió. Una tienda fallida u omitida no tiene pedido.';
const PEDIR_TEXTO = 'A pedir: unidades y valor de la Cantidad a pedir (lo que el comprador va a mandar), no del sugerido del motor.';

function Encabezado({ texto, ayuda, pegada }) {
  return (
    <th style={{ ...thStyle, ...stickyHeadStyle, ...(pegada ? { ...stickyColStyle, zIndex: 4, top: 0 } : {}) }}>
      <span style={{ display: 'inline-flex', alignItems: 'center' }}>
        {texto}
        {ayuda && <InfoTooltip text={ayuda} />}
      </span>
    </th>
  );
}

export default function TiendasTable({ tiendas, onOpen }) {
  return (
    <MotoredTableScroll maxHeight="70vh">
      <table style={{ ...tablaStyle, width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
            <Encabezado texto="Tienda" pegada />
            <Encabezado texto="Cálculo" ayuda={CALCULO_TEXTO} />
            <Encabezado texto="Pedido" ayuda={ESTADO_PEDIDO_TEXTO} />
            <Encabezado texto="A pedir" ayuda={PEDIR_TEXTO} />
            <Encabezado texto="Último evento" />
            <Encabezado texto="Acción" />
          </tr>
        </thead>
        <tbody>
          {tiendas.map((t) => <TiendaFila key={t.sucursal_id} tienda={t} onOpen={onOpen} />)}
        </tbody>
      </table>
    </MotoredTableScroll>
  );
}
