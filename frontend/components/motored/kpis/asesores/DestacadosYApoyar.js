import { useState } from 'react';
import { BarList, Chip, SegmentedToggle } from '../charts';
import { periodoCorto } from '../periodo';
import { COLOR } from '../tokens';
import { CABECERA, NUM, TARJETA, TITULO } from '../ventas/estilos';
import { COLUMNAS_MEZCLA, bottomCumplimiento, filaMezcla, topVenta } from './datos';

const VISTAS = [{ id: 'venta', label: 'Venta' }, { id: 'mezcla', label: 'Mezcla' }];
const ALTO = 380;
const COLUMNA = { minWidth: 0, padding: 14, borderRadius: 14, border: `1px solid ${COLOR.track}` };
const NOTA = { margin: '10px 0 0', fontSize: 11.5, color: COLOR.muted };

function Matriz({ items }) {
  return (
    <div style={{ overflow: 'auto', maxHeight: ALTO, marginTop: 12 }}>
      <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 5, minWidth: 420, fontSize: 12.5 }}>
        <thead>
          <tr style={{ color: COLOR.muted, fontSize: 11, textTransform: 'uppercase', letterSpacing: '.04em' }}>
            <th style={{ fontWeight: 700, padding: '4px 6px' }}><div style={{ textAlign: 'left' }}>Asesor</div></th>
            {COLUMNAS_MEZCLA.map(([linea, texto]) => <th key={linea} style={{ fontWeight: 700 }}>{texto}</th>)}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const fila = filaMezcla(item);
            return (
              <tr key={fila.id} data-testid="mezcla-fila">
                <td style={{ padding: '4px 6px', maxWidth: 170 }}>
                  <div style={{ fontWeight: 700, textAlign: 'left', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{fila.name}</div>
                </td>
                {fila.cells.map((c, i) => (
                  <td
                    key={i} data-testid="mezcla-celda"
                    style={{ ...NUM, padding: '9px 4px', borderRadius: 8, fontWeight: 700, background: `rgba(29, 78, 137, ${c.alpha.toFixed(2)})`, color: c.dark ? '#FFFFFF' : COLOR.ink }}
                  >
                    {c.text}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Columna({ nombre, titulo, chip, vista, items, children }) {
  return (
    <section aria-label={nombre} style={COLUMNA}>
      <div style={{ ...CABECERA, gap: 8 }}>
        <h3 style={{ ...TITULO, fontSize: 14 }}>{titulo}</h3>
        {chip}
      </div>
      <div style={{ marginTop: 14 }}>
        {vista === 'venta' ? <BarList items={items} maxHeight={ALTO} /> : <Matriz items={items} />}
      </div>
      {children}
    </section>
  );
}

/** "Asesores destacados y a apoyar": best sellers and lowest compliance, as bars or as line-mix matrices. */
export default function DestacadosYApoyar({ data }) {
  const [vista, setVista] = useState('venta');
  const periodo = periodoCorto(data.meses);
  const bottom = bottomCumplimiento(data);
  return (
    <section aria-label="Asesores destacados y a apoyar" style={TARJETA}>
      <div style={CABECERA}>
        <h2 style={TITULO}>Asesores destacados y a apoyar</h2>
        <SegmentedToggle options={VISTAS} value={vista} onChange={setVista} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 340px), 1fr))', gap: 16, marginTop: 14 }}>
        <Columna nombre="Top 10 · venta" titulo={`Top 10 · venta ${periodo}`} chip={<Chip text="▲ mayor venta" variant="up" />} vista={vista} items={topVenta(data)} />
        <Columna nombre="Bottom 10 · cumplimiento" titulo={`Bottom 10 · cumplimiento ${periodo}`} chip={<Chip text="▼ menor cumplimiento" variant="down" />} vista={vista} items={bottom.items}>
          {bottom.sinPresupuesto > 0 && (
            <p style={NOTA}>
              {bottom.sinPresupuesto} {bottom.sinPresupuesto === 1 ? 'asesor sin presupuesto no aparece' : 'asesores sin presupuesto no aparecen'} en este ranking.
            </p>
          )}
        </Columna>
      </div>
    </section>
  );
}
