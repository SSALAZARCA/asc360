'use client';
/**
 * Tiendas of one corrida with their lifecycle actions (`ciclo`, none for a read-only table). Scrolls inside its box;
 * first column and header stay in view. With `topes` (the cap summary, mode on) it adds the Tope column.
 */
import InfoTooltip from '../InfoTooltip';
import MotoredTableScroll from '../MotoredTableScroll';
import TiendaFila from './TiendaFila';
import { ESTADO_PEDIDO_TEXTO } from './EstadoPedidoBadge';
import { TOPE_TEXTO } from './TopeBanner';
import { stickyColStyle, stickyHeadStyle, stickyRightStyle, tablaStyle, thCompactStyle as thStyle } from './styles';

const CALCULO_TEXTO = 'Cálculo: si el motor pudo calcular la tienda (OK), falló (Fallida) o se omitió. Una tienda fallida u omitida no tiene pedido.';
const PEDIR_TEXTO = 'A pedir: unidades y valor de la Cantidad a pedir (lo que el comprador va a mandar), no del sugerido del motor.';

// The header cells of the sticky first and last columns sit above both the body cells and the other headers.
const PEGADA_IZQUIERDA = { ...stickyColStyle, zIndex: 4, top: 0 };
const PEGADA_DERECHA = { ...stickyRightStyle, zIndex: 4, top: 0 };

function Encabezado({ texto, ayuda, pegada, derecha }) {
  return (
    <th style={{ ...thStyle, ...stickyHeadStyle, ...(pegada ? PEGADA_IZQUIERDA : {}), ...(derecha ? PEGADA_DERECHA : {}) }}>
      <span style={{ display: 'inline-flex', alignItems: 'center' }}>
        {texto}
        {ayuda && <InfoTooltip text={ayuda} />}
      </span>
    </th>
  );
}

export default function TiendasTable({ tiendas, onOpen, ciclo, topes }) {
  const porSucursal = topes ? Object.fromEntries(topes.tiendas.map((t) => [t.sucursal_id, t])) : null;
  return (
    <MotoredTableScroll maxHeight="70vh">
      <table aria-label="Tiendas del pedido" style={{ ...tablaStyle, width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
            <Encabezado texto="Tienda" pegada />
            <Encabezado texto="Cálculo" ayuda={CALCULO_TEXTO} />
            <Encabezado texto="Pedido" ayuda={ESTADO_PEDIDO_TEXTO} />
            <Encabezado texto="A pedir" ayuda={PEDIR_TEXTO} />
            {topes && <Encabezado texto="Tope" ayuda={TOPE_TEXTO} />}
            <Encabezado texto="Último evento" />
            <Encabezado texto="Acción" derecha />
          </tr>
        </thead>
        <tbody>
          {tiendas.map((t) => (
            <TiendaFila
              key={t.sucursal_id} tienda={t} onOpen={onOpen} ciclo={ciclo}
              conTope={Boolean(porSucursal)} tope={porSucursal ? porSucursal[t.sucursal_id] : undefined}
            />
          ))}
        </tbody>
      </table>
    </MotoredTableScroll>
  );
}
