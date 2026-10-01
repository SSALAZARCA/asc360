/** Per-class summary of ONE tienda: sugerido (engine) next to a pedir (the buyer's quantities). */
import { formatCOP } from '../../../lib/motored/formatCOP';
import MotoredTableScroll from '../MotoredTableScroll';
import { unidades } from './formato';
import { numStyle, tdStyle, thStyle } from './styles';

const TITULOS = ['Clase', 'Referencias', 'Sugerido (uds)', 'A pedir (uds)', 'Valor a pedir', 'Peso %'];

/** Joins `resumen` (sugerido) and `resumen_a_pedir` by class for one tienda. */
export function filasPorClase(sucursalId, resumen = [], aPedir = []) {
  const sugerido = new Map(resumen.filter((f) => f.sucursal_id === sucursalId).map((f) => [f.clase, f]));
  return aPedir
    .filter((f) => f.sucursal_id === sucursalId)
    .map((f) => ({ ...f, sugerido: sugerido.get(f.clase)?.unidades }));
}

export default function ResumenClasesTable({ filas }) {
  if (filas.length === 0) return null;
  return (
    <MotoredTableScroll>
      <table aria-label="Resumen por clase" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
            {TITULOS.map((t) => <th key={t} style={thStyle}>{t}</th>)}
          </tr>
        </thead>
        <tbody>
          {filas.map((f) => (
            <tr key={f.clase} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)', fontWeight: f.clase === 'TOTAL' ? 700 : 400 }}>
              <td style={tdStyle}>{f.clase}</td>
              <td style={{ ...tdStyle, ...numStyle }}>{f.referencias}</td>
              <td style={{ ...tdStyle, ...numStyle }}>{unidades(f.sugerido)}</td>
              <td style={{ ...tdStyle, ...numStyle }}>{unidades(f.unidades)}</td>
              <td style={{ ...tdStyle, ...numStyle }}>{formatCOP(f.valor)}</td>
              <td style={{ ...tdStyle, ...numStyle }}>{unidades(f.porcentaje_peso)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </MotoredTableScroll>
  );
}
