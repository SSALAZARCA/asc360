'use client';
/** Corridas table (scrolls horizontally inside its container on tablet). */
import InfoTooltip from '../InfoTooltip';
import MotoredTableScroll from '../MotoredTableScroll';
import CorridaFila from './CorridaFila';
import { thStyle } from './styles';

const CORTE_TEXTO = 'Fecha de corte: el día hasta el que se toman las ventas y el inventario para calcular el pedido.';
const CALCULO_TEXTO = 'Cálculo: avance del cálculo de la corrida. Cada tienda tiene después su propio pedido.';
const PEDIDOS_TEXTO = 'Estado del pedido: cada tienda tiene el suyo (Borrador, Cerrado o Enviado). Aquí se cuenta cuántas van en cada punto.';

function Encabezado({ texto, ayuda }) {
  return (
    <th style={thStyle}>
      <span style={{ display: 'inline-flex', alignItems: 'center' }}>
        {texto}
        {ayuda && <InfoTooltip text={ayuda} />}
      </span>
    </th>
  );
}

export default function CorridasTable({ corridas, onOpen, onAnular, onTerminal }) {
  return (
    <MotoredTableScroll>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
            <Encabezado texto="Acción" />
            <Encabezado texto="Corrida" />
            <Encabezado texto="Corte" ayuda={CORTE_TEXTO} />
            <Encabezado texto="Cálculo" ayuda={CALCULO_TEXTO} />
            <Encabezado texto="Pedidos" ayuda={PEDIDOS_TEXTO} />
            <Encabezado texto="Creada" />
          </tr>
        </thead>
        <tbody>
          {corridas.map((c) => (
            <CorridaFila key={c.id} corrida={c} onOpen={onOpen} onAnular={onAnular} onTerminal={onTerminal} />
          ))}
        </tbody>
      </table>
    </MotoredTableScroll>
  );
}
