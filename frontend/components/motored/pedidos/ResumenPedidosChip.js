/** "3 de 47 enviadas" plus the closed and draft counts of the tienda pedidos. */
import { mutedStyle } from './styles';

export default function ResumenPedidosChip({ pedidos }) {
  if (!pedidos) return <span style={mutedStyle}>—</span>;
  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', gap: '2px' }}>
      <span style={{ fontSize: '0.8rem', fontWeight: 700 }}>{`${pedidos.enviados} de ${pedidos.total} enviadas`}</span>
      <span style={mutedStyle}>{`Cerrados ${pedidos.cerrados} · Borrador ${pedidos.borrador}`}</span>
    </span>
  );
}
