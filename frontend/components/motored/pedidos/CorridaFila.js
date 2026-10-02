'use client';
/** One row of the corridas table. */
import InfoTooltip from '../InfoTooltip';
import MotoredIconAction from '../MotoredIconAction';
import EstadoCalculoBadge from './EstadoCalculoBadge';
import ResumenPedidosChip from './ResumenPedidosChip';
import ProgresoCorrida from './ProgresoCorrida';
import PruebaBadge from './PruebaBadge';
import { avisoAntiguedad, estaCalculando, fechaCorta, puedeAnular } from './reglas';
import { mutedStyle, tdStyle } from './styles';

const AVISO_STYLE = { display: 'inline-flex', alignItems: 'center', fontSize: '0.7rem', fontWeight: 700, color: 'var(--motored-warning, #d97706)' };
const INVALIDADA_TEXTO = 'Datos invalidados: se anuló una carga que esta corrida usó, por eso ya no se puede cerrar ninguna tienda. Calcule una corrida nueva.';

function Calculo({ corrida, onTerminal }) {
  const antiguedad = avisoAntiguedad(corrida);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'flex-start' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
        <EstadoCalculoBadge estado={corrida.estado} />
        {corrida.es_escenario && <PruebaBadge />}
      </span>
      {estaCalculando(corrida.estado) && (
        <ProgresoCorrida corridaId={corrida.id} estado={corrida.estado} onTerminal={onTerminal} />
      )}
      {corrida.invalidada && (
        <span style={AVISO_STYLE}>
          Datos invalidados
          <InfoTooltip text={INVALIDADA_TEXTO} />
        </span>
      )}
      {antiguedad && (
        <span style={AVISO_STYLE}>
          {antiguedad.texto}
          <InfoTooltip text={antiguedad.ayuda} />
        </span>
      )}
    </div>
  );
}

export default function CorridaFila({ corrida, onOpen, onAnular, onTerminal }) {
  return (
    <tr style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
      <td style={tdStyle}>
        <MotoredIconAction action="Ver detalle" touch onClick={() => onOpen(corrida.id)} />
        {puedeAnular(corrida)
          ? <MotoredIconAction action="Anular" touch onClick={() => onAnular(corrida)} />
          : <span aria-hidden="true" style={{ display: 'inline-block', width: '44px' }} />}
      </td>
      <td style={tdStyle}>
        <button
          type="button" className="motored-row-action" style={{ minHeight: '44px' }}
          onClick={() => onOpen(corrida.id)}
        >
          {corrida.codigo}
        </button>
      </td>
      <td style={tdStyle}>{fechaCorta(corrida.fecha_corte)}</td>
      <td style={{ ...tdStyle, whiteSpace: 'normal' }}><Calculo corrida={corrida} onTerminal={onTerminal} /></td>
      <td style={tdStyle}><ResumenPedidosChip pedidos={corrida.pedidos} /></td>
      <td style={{ ...tdStyle, ...mutedStyle }}>{fechaCorta(corrida.created_at)}</td>
    </tr>
  );
}
