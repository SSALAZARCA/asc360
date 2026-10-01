'use client';
/** One line of the pedido (read-only). */
import { formatCOP } from '../../../lib/motored/formatCOP';
import CantidadCelda from './CantidadCelda';
import { etiquetaExclusion, etiquetaQuiebre, unidades } from './formato';
import { mutedStyle, numStyle, stickyColStyle, tdCompactStyle as tdStyle } from './styles';

export default function LineaFila({ linea, onHistorial }) {
  const excluida = Boolean(linea.motivo_exclusion);
  return (
    <tr style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)', opacity: excluida ? 0.65 : 1 }}>
      <td style={{ ...tdStyle, ...stickyColStyle, fontWeight: 600 }}>{linea.codigo_referencia}</td>
      <td style={{ ...tdStyle, whiteSpace: 'normal', minWidth: '130px' }}>
        {linea.nombre_parte}
        {excluida && <span style={{ ...mutedStyle, display: 'block' }}>{`Excluida: ${etiquetaExclusion(linea.motivo_exclusion)}`}</span>}
      </td>
      <td style={tdStyle}>{linea.clase || '—'}</td>
      <td style={{ ...tdStyle, ...numStyle }}>{linea.unidad_empaque}</td>
      <td style={{ ...tdStyle, ...numStyle }}>{formatCOP(linea.precio)}</td>
      <td style={{ ...tdStyle, ...numStyle }}>{unidades(linea.pedido_sugerido)}</td>
      <td style={{ ...tdStyle, ...numStyle }}><CantidadCelda linea={linea} onHistorial={onHistorial} /></td>
      <td style={{ ...tdStyle, ...numStyle }}>{formatCOP(linea.valor_pedido)}</td>
      <td style={tdStyle}>{etiquetaQuiebre(linea.estado_quiebre)}</td>
    </tr>
  );
}
