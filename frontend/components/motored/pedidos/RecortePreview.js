'use client';
/** The lines a recorte proposal would cut: quantity now, quantity proposed and value freed. Scrolls inside its box. */
import { formatCOP } from '../../../lib/motored/formatCOP';
import MotoredTableScroll from '../MotoredTableScroll';
import { unidades } from './formato';
import { numStyle, stickyHeadStyle, tablaStyle, tdCompactStyle as tdStyle, thCompactStyle as thStyle } from './styles';

const COLUMNAS = ['Código', 'Nombre', 'Clase', 'Actual', 'Propuesto', 'Valor que libera'];

export default function RecortePreview({ recortes }) {
  return (
    <MotoredTableScroll maxHeight="40vh">
      <table aria-label="Líneas que se recortarían" style={{ ...tablaStyle, width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
            {COLUMNAS.map((titulo) => <th key={titulo} style={{ ...thStyle, ...stickyHeadStyle }}>{titulo}</th>)}
          </tr>
        </thead>
        <tbody>
          {recortes.map((r) => (
            <tr key={r.linea_id} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
              <td style={{ ...tdStyle, fontWeight: 600 }}>{r.codigo}</td>
              <td style={{ ...tdStyle, whiteSpace: 'normal', minWidth: '130px' }}>{r.nombre}</td>
              <td style={tdStyle}>{r.clase_abc}</td>
              <td style={{ ...tdStyle, ...numStyle }}>{unidades(r.pedido_actual)}</td>
              <td style={{ ...tdStyle, ...numStyle, fontWeight: 700 }}>{unidades(r.pedido_propuesto)}</td>
              <td style={{ ...tdStyle, ...numStyle }}>{formatCOP(r.valor_recortado)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </MotoredTableScroll>
  );
}
