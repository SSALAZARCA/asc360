'use client';
/** One tienda of the corrida (read-only): calculation, pedido state, a pedir, last event. */
import MotoredIconAction from '../MotoredIconAction';
import AccionesTienda from './AccionesTienda';
import { formatCOP } from '../../../lib/motored/formatCOP';
import EstadoCalculoBadge from './EstadoCalculoBadge';
import EstadoPedidoBadge from './EstadoPedidoBadge';
import { fechaCorta } from './reglas';
import { etiquetaEvento, fechaHora, unidades } from './formato';
import { mutedStyle, numStyle, stickyColStyle, stickyRightStyle, tdCompactStyle } from './styles';

const fallaStyle = { background: 'var(--motored-danger-bg, #fdecea)' };
// Compact cells whose text may wrap: on a tablet the table must fit its box, or the sticky Acción column would cover them.
const tdStyle = tdCompactStyle;
const ajusteStyle = { ...tdCompactStyle, whiteSpace: 'normal' };

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

/** Event, who and when; it wraps instead of being cut, and the whole sentence is also its tooltip. */
function UltimoEvento({ evento }) {
  if (!evento) return <span style={mutedStyle}>Sin movimientos</span>;
  const quien = evento.usuario ? ` por ${evento.usuario}` : '';
  const que = `${etiquetaEvento(evento.evento)}${quien}`;
  return (
    <span title={`${que} · ${fechaHora(evento.creado_en)}`} style={{ display: 'flex', flexDirection: 'column' }}>
      <span style={{ fontSize: '0.8rem' }}>{que}</span>
      <span style={mutedStyle}>{fechaHora(evento.creado_en)}</span>
    </span>
  );
}

/** Cap of the tienda: the excess, within the cap, no cap, or a dash when the tienda has no pedido. */
function CeldaTope({ tope }) {
  if (!tope) return <span style={mutedStyle}>—</span>;
  if (tope.tope == null) return <span style={mutedStyle}>Sin tope</span>;
  if (Number(tope.exceso) > 0) {
    return <span style={{ fontWeight: 700, color: 'var(--motored-warning, #d97706)', ...numStyle }}>{`Excede ${formatCOP(tope.exceso)}`}</span>;
  }
  return <span style={mutedStyle}>Dentro del tope</span>;
}

const casillaStyle = { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: '24px', flex: 'none' };

/** The tienda name; with `ciclo`, a checkbox slot (empty when the tienda has nothing to batch) keeps the names aligned. */
function NombreTienda({ tienda, ciclo }) {
  const acciones = tienda.acciones || {};
  if (!ciclo) return tienda.nombre;
  const seleccionable = Boolean(acciones.cerrar || acciones.enviar);
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minHeight: '44px', cursor: seleccionable ? 'pointer' : 'default', textAlign: 'left' }}>
      <span style={casillaStyle}>
        {seleccionable && (
          <input
            type="checkbox" aria-label={`Seleccionar ${tienda.nombre}`} checked={ciclo.marcadas.has(tienda.sucursal_id)}
            onChange={() => ciclo.alternar(tienda.sucursal_id)}
          />
        )}
      </span>
      {tienda.nombre}
    </label>
  );
}

/** `conTope` adds the cap cell (`tope` is the tienda row of the cap summary, absent for a tienda without pedido). */
export default function TiendaFila({ tienda, onOpen, ciclo, conTope = false, tope }) {
  const conPedido = tienda.estado_pedido != null;
  // Flagged only when its calculation failed: a scenario tienda has no pedido either, and that is not a failure.
  const marca = tienda.estado === 'OK' ? {} : fallaStyle;
  return (
    <tr style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)', ...marca }}>
      <td style={{ ...ajusteStyle, ...stickyColStyle, ...marca, fontWeight: 600 }}><NombreTienda tienda={tienda} ciclo={ciclo} /></td>
      <td style={ajusteStyle}><Calculo tienda={tienda} /></td>
      <td style={ajusteStyle}><Pedido tienda={tienda} /></td>
      <td style={{ ...tdStyle, ...numStyle }}>
        <span style={{ display: 'flex', flexDirection: 'column' }}>
          <span>{unidades(tienda.unidades_a_pedir)}</span>
          <span style={mutedStyle}>{formatCOP(tienda.valor_a_pedir)}</span>
        </span>
      </td>
      {conTope && <td style={ajusteStyle}><CeldaTope tope={tope} /></td>}
      <td style={ajusteStyle}><UltimoEvento evento={tienda.ultimo_evento} /></td>
      <td style={{ ...tdStyle, ...stickyRightStyle, ...marca }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          {conPedido && <MotoredIconAction action="Ver pedido" touch onClick={() => onOpen(tienda.sucursal_id)} />}
          {ciclo && <AccionesTienda tienda={tienda} alAccionar={ciclo.alAccionar} ocupado={ciclo.ocupado} />}
        </div>
      </td>
    </tr>
  );
}
