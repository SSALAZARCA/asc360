/**
 * One row of the differences table (WU12): the state pill derived from the
 * reconteo and the thresholds, and the leader's action. Reconteos exist
 * only in EN_RECONTEO (the backend rejects them during the first round).
 */
import { formatCantidad, formatPesosConSigno, parejaCorta } from './conteosFormato';
import { monoStyle, mutedStyle, pildoraStyle } from './estilos';

const td = { padding: '12px 8px', verticalAlign: 'middle' };
const tdNum = { ...td, textAlign: 'right', ...monoStyle, whiteSpace: 'nowrap' };

const PILDORAS = {
  critica: ['var(--motored-danger, #c0392b)', '#ffffff'],
  recontando: ['var(--motored-warning-bg, #fef3e2)', 'var(--motored-data-mid-ink, #8a4104)'],
  lista: ['var(--motored-success-bg, #ecfdf3)', 'var(--motored-success, #15803d)'],
  neutra: ['var(--motored-surface-alt, #f4f4f5)', 'var(--motored-text, #1a1a18)'],
};

/** Same rule as the closed result's `confirmada`: the reconteo kept the sign
 * of the round-1 difference. A zero or a flipped sign is a correction. */
function reconteoConfirma(fila) {
  const ronda1 = Math.sign(Number(fila.contado_ronda1) - Number(fila.sistema));
  const final = Math.sign(Number(fila.diferencia));
  return final !== 0 && final === ronda1;
}

/** [texto, tono] of the state pill. */
export function estadoDiferencia(fila, umbrales) {
  const r = fila.reconteo;
  if (r?.estado === 'ASIGNADO') return [`Recontando · ${parejaCorta(r.sesion?.etiqueta)}`, 'recontando'];
  if (r?.estado === 'PENDIENTE') return ['Reconteo sin asignar', 'recontando'];
  if (r?.estado === 'TERMINADO') {
    return reconteoConfirma(fila) ? ['Confirmada en reconteo', 'lista'] : ['Corregida en reconteo', 'lista'];
  }
  if (fila.critico) return ['Crítica', 'critica'];
  if (fila.sin_costo) return ['Sin costo', 'neutra'];
  const umbral = Number(umbrales.reconteo);
  if (Number.isFinite(umbral) && Math.abs(Number(fila.valor)) >= umbral) return ['Sobre el umbral', 'neutra'];
  return ['Bajo el umbral', 'neutra'];
}

function Accion({ fila, onPedir, onAsignar, onCancelar, ocupado }) {
  const r = fila.reconteo;
  if (!r) {
    return (
      <button type="button" className={`motored-btn ${fila.critico ? 'motored-btn-primary' : 'motored-btn-secondary'}`} disabled={ocupado} onClick={() => onPedir(fila.codigo)}>
        Pedir reconteo
      </button>
    );
  }
  if (r.estado === 'TERMINADO') return <span style={mutedStyle}>Lista para ajuste</span>;
  return (
    <div style={{ display: 'flex', gap: '0.4rem', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
      <button type="button" className="motored-btn motored-btn-secondary" disabled={ocupado} onClick={() => onAsignar(fila)}>
        {r.estado === 'ASIGNADO' ? 'Reasignar' : 'Asignar'}
      </button>
      <button type="button" className="motored-btn motored-btn-tertiary" disabled={ocupado} aria-label="Cancelar reconteo" onClick={() => onCancelar(r.id)}>
        Cancelar
      </button>
    </div>
  );
}

export default function DiferenciaFila({ fila, umbrales, opera, enReconteo, ...acciones }) {
  const [texto, tono] = estadoDiferencia(fila, umbrales);
  const negativo = Number(fila.valor) < 0;
  const accion = opera && enReconteo ? <Accion fila={fila} {...acciones} /> : <span style={mutedStyle}>—</span>;
  return (
    <tr style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)', background: fila.critico ? 'var(--motored-danger-bg, #fdecea)' : undefined }}>
      <td style={{ ...td, paddingLeft: '1.25rem' }}>
        <div style={{ ...monoStyle, fontWeight: 600 }}>{fila.codigo}</div>
        <div style={{ ...mutedStyle, fontSize: '0.75rem' }}>{fila.descripcion || 'Código fuera del catálogo'}</div>
      </td>
      <td style={{ ...td, fontSize: '0.8rem' }}>{fila.ubicaciones.join(' · ') || '—'}</td>
      <td style={tdNum}>{formatCantidad(fila.sistema)}</td>
      <td style={tdNum}>{formatCantidad(fila.contado)}</td>
      <td style={{ ...tdNum, fontWeight: 600, color: negativo ? 'var(--motored-danger, #c0392b)' : 'var(--motored-success, #15803d)' }}>
        {fila.valor == null ? 'Sin costo' : formatPesosConSigno(fila.valor)}
      </td>
      <td style={td}><span style={pildoraStyle(...PILDORAS[tono])}>{texto}</span></td>
      <td style={{ ...td, textAlign: 'right', paddingRight: '1.25rem' }}>{accion}</td>
    </tr>
  );
}
