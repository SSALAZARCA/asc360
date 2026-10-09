/** The result lines of a closed conteo (WU12). Every difference goes to the store's principal bodega. */
import MotoredTableScroll from '../MotoredTableScroll';
import { formatCantidad, formatPesos, formatPesosConSigno } from './conteosFormato';
import { MAX_FILAS } from './DiferenciasTabla';
import { cardStyle, h2Style, monoStyle, mutedStyle, tdStyle, thStyle } from './estilos';

const num = { ...tdStyle, textAlign: 'right', ...monoStyle };
const thNum = { ...thStyle, textAlign: 'right' };

function reconteo(linea) {
  if (!linea.con_reconteo) return '—';
  if (linea.confirmada == null) return 'Sin terminar';
  return linea.confirmada ? 'Confirmada' : 'Corregida';
}

export default function ResultadoTabla({ resultado }) {
  const lineas = resultado.items.slice(0, MAX_FILAS);
  return (
    <div style={cardStyle}>
      <h2 style={h2Style}>Resultado por referencia</h2>
      <p style={{ ...mutedStyle, margin: 0 }}>Toda la diferencia de cada referencia se ajusta en la bodega principal {resultado.bodega || ''}.</p>
      <MotoredTableScroll maxHeight="70vh">
        <table style={{ width: '100%', minWidth: '900px', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
          <thead>
            <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
              <th style={thStyle}>Referencia</th><th style={thStyle}>Bodega</th><th style={thNum}>Sistema</th>
              <th style={thNum}>Contado</th><th style={thNum}>Diferencia</th><th style={thNum}>Costo unit.</th>
              <th style={thNum}>Valor</th><th style={thStyle}>Ubicaciones</th><th style={thStyle}>Reconteo</th>
            </tr>
          </thead>
          <tbody>
            {lineas.map((l) => (
              <tr key={l.codigo} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)', background: l.critico ? 'var(--motored-danger-bg, #fdecea)' : undefined }}>
                <td style={tdStyle}>
                  <div style={{ ...monoStyle, fontWeight: 600 }}>{l.codigo}</div>
                  <div style={{ ...mutedStyle, fontSize: '0.75rem' }}>{l.descripcion || 'Código fuera del catálogo'}</div>
                </td>
                <td style={tdStyle}>{l.bodega || '—'}</td>
                <td style={num}>{formatCantidad(l.sistema)}</td>
                <td style={num}>{formatCantidad(l.contado)}</td>
                <td style={num}>{formatCantidad(l.diferencia)}</td>
                <td style={num}>{formatPesos(l.costo_unitario)}</td>
                <td style={{ ...num, fontWeight: 600 }}>{l.valor == null ? 'Sin costo' : formatPesosConSigno(l.valor)}</td>
                <td style={tdStyle}>{l.ubicaciones.join(' · ') || '—'}</td>
                <td style={tdStyle}>{reconteo(l)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </MotoredTableScroll>
      {resultado.items.length > MAX_FILAS && (
        <p style={{ ...mutedStyle, margin: 0 }}>Se muestran {MAX_FILAS} de {resultado.items.length}. El Excel de ajustes trae todas.</p>
      )}
    </div>
  );
}
