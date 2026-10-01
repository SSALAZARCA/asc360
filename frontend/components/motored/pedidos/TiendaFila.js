'use client';
/** One tienda of the corrida (read-only): calculation, pedido state, a pedir, last event. */
import MotoredIconAction from '../MotoredIconAction';
import { formatCOP } from '../../../lib/motored/formatCOP';
import EstadoCalculoBadge from './EstadoCalculoBadge';
import EstadoPedidoBadge from './EstadoPedidoBadge';
import { fechaCorta } from './reglas';
import { etiquetaEvento, fechaHora, unidades } from './formato';
import { mutedStyle, numStyle, stickyColStyle, tdStyle } from './styles';

const fallaStyle = { background: 'var(--motored-danger-bg, #fdecea)' };

function Calculo({ tienda }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', alignItems: 'flex-start' }}>
      <EstadoCalculoBadge estado={tienda.estado} />
      {tienda.mensaje && <span style={{ ...mutedStyle, whiteSpace: 'normal' }}>{tienda.mensaje}</span>}
      {tienda.codigo && <span style={mutedStyle}>{tienda.codigo}</span>}
    </div>
  );
}

function Pedido({ tienda }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', alignItems: 'flex-start' }}>
      <EstadoPedidoBadge estado={tienda.estado_pedido} />
      {tienda.envio && (
        <span style={mutedStyle}>{`Orden ${tienda.envio.numero_orden} · ${fechaCorta(tienda.envio.fecha_envio)}`}</span>
      )}
    </div>
  );
}

function UltimoEvento({ evento }) {
  if (!evento) return <span style={mutedStyle}>Sin movimientos</span>;
  const quien = evento.usuario ? ` por ${evento.usuario}` : '';
  return (
    <span style={{ display: 'flex', flexDirection: 'column' }}>
      <span style={{ fontSize: '0.8rem' }}>{`${etiquetaEvento(evento.evento)}${quien}`}</span>
      <span style={mutedStyle}>{fechaHora(evento.creado_en)}</span>
    </span>
  );
}

export default function TiendaFila({ tienda, onOpen }) {
  const conPedido = tienda.estado_pedido != null;
  return (
    <tr style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)', ...(conPedido ? {} : fallaStyle) }}>
      <td style={{ ...tdStyle, ...stickyColStyle, ...(conPedido ? {} : fallaStyle), fontWeight: 600 }}>{tienda.nombre}</td>
      <td style={{ ...tdStyle, whiteSpace: 'normal' }}><Calculo tienda={tienda} /></td>
      <td style={tdStyle}><Pedido tienda={tienda} /></td>
      <td style={{ ...tdStyle, ...numStyle }}>
        <span style={{ display: 'flex', flexDirection: 'column' }}>
          <span>{unidades(tienda.unidades_a_pedir)}</span>
          <span style={mutedStyle}>{formatCOP(tienda.valor_a_pedir)}</span>
        </span>
      </td>
      <td style={tdStyle}><UltimoEvento evento={tienda.ultimo_evento} /></td>
      <td style={tdStyle}>
        {conPedido && <MotoredIconAction action="Ver pedido" touch onClick={() => onOpen(tienda.sucursal_id)} />}
      </td>
    </tr>
  );
}
