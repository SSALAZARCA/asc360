import { miles } from '../format';
import { COLOR } from '../tokens';
import { HEAT_LEYENDA, heatLevel, heatRows } from './geometry';

const NIVEL_LEYENDA = [1.2, 1.1, 1, 0.9, 0.8, 0.5];

function Leyenda() {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 12px', fontSize: 11.5, color: COLOR.muted, marginTop: 10 }}>
      {HEAT_LEYENDA.map((texto, i) => (
        <span key={texto} data-testid="heat-legend-item" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 14, height: 14, borderRadius: 4, border: `1px solid ${COLOR.line}`, background: heatLevel(NIVEL_LEYENDA[i]).bg }} />
          {texto}
        </span>
      ))}
    </div>
  );
}

const CABECERA = {
  position: 'sticky', top: 0, background: COLOR.surface, zIndex: 1, fontSize: 11, color: COLOR.muted,
  textTransform: 'uppercase', letterSpacing: '.04em', fontWeight: 500, padding: '4px 0',
};

/**
 * Rows x columns table; each cell is colored against its row's own average (6 levels, teal above, violet below).
 * `rowHeader` titles the name column. `rows` [{name, values[]}] (0 or null = no data), `maxHeight` scrolls inside the box, header stays sticky.
 */
export default function Heatmap({ columns, rows, formatValue = miles, maxHeight = 380, legend = true, nameWidth = 160, rowHeader }) {
  return (
    <div>
      <div data-testid="heatmap-scroll" style={{ overflow: 'auto', maxHeight, marginTop: 12 }}>
        <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 5, minWidth: 420, fontSize: 12.5 }}>
          <thead>
            <tr>
              {/* globals.css forces `text-align: center !important` on cells, so the left alignment lives in a block inside the cell. */}
              <th style={{ ...CABECERA, minWidth: nameWidth }}><div style={{ textAlign: 'left' }}>{rowHeader}</div></th>
              {columns.map((c) => <th key={c} style={CABECERA}>{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {heatRows(rows).map((fila) => (
              <tr key={fila.id ?? fila.name}>
                <td style={{ maxWidth: nameWidth }}>
                  <div style={{ fontWeight: 700, textAlign: 'left', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{fila.name}</div>
                </td>
                {fila.cells.map((c, i) => (
                  <td
                    key={i} data-testid="heat-cell" data-level={c.level ?? 'none'}
                    style={{ background: c.bg, color: c.fg, textAlign: 'center', borderRadius: 6, padding: '6px 4px', fontVariantNumeric: 'tabular-nums' }}
                  >
                    {c.value === null ? '–' : formatValue(c.value)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {legend && <Leyenda />}
    </div>
  );
}
