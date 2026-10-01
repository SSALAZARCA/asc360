'use client';
/** Totals of the comparison: the whole network in a strip and every compared tienda in a table (units and value, both sides). */
import MotoredTableScroll from '../MotoredTableScroll';
import { formatCOP } from '../../../lib/motored/formatCOP';
import DeltaCelda from './DeltaCelda';
import { sumarTotales } from './comparacion';
import { unidades } from './formato';
import { numStyle, resumenRedStyle, stickyColStyle, stickyHeadStyle, tablaStyle, tdCompactStyle, thCompactStyle } from './styles';

const COLUMNAS = [
  { id: 'tienda', texto: 'Tienda' }, { id: 'u-real', texto: 'Unidades real' }, { id: 'u-prueba', texto: 'Unidades prueba' },
  { id: 'u-dif', texto: 'Diferencia' }, { id: 'v-real', texto: 'Valor real' }, { id: 'v-prueba', texto: 'Valor prueba' },
  { id: 'v-dif', texto: 'Diferencia' },
];

export function ResumenComparacion({ totales }) {
  const t = sumarTotales(totales);
  return (
    <div role="group" aria-label="Resumen de la red" style={resumenRedStyle}>
      <span style={{ fontWeight: 400 }}>Toda la red</span>
      <span>{`Real ${unidades(t.unidadesReal)} unidades`}</span>
      <span>{`Prueba ${unidades(t.unidadesPrueba)} unidades`}</span>
      <DeltaCelda valor={t.diferenciaUnidades} sufijo=" unidades" />
      <DeltaCelda valor={t.diferenciaValor} moneda />
    </div>
  );
}

function Fila({ total }) {
  const celda = { ...tdCompactStyle, ...numStyle };
  return (
    <tr style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
      <td style={{ ...tdCompactStyle, ...stickyColStyle, textAlign: 'left', fontWeight: 600 }}>{total.nombre}</td>
      <td style={celda}>{unidades(total.unidades_real)}</td>
      <td style={celda}>{unidades(total.unidades_prueba)}</td>
      <td style={celda}><DeltaCelda valor={total.diferencia_unidades} /></td>
      <td style={celda}>{formatCOP(total.valor_real)}</td>
      <td style={celda}>{formatCOP(total.valor_prueba)}</td>
      <td style={celda}><DeltaCelda valor={total.diferencia_valor} moneda /></td>
    </tr>
  );
}

export default function ComparacionTotales({ totales }) {
  return (
    <MotoredTableScroll maxHeight="40vh">
      <table aria-label="Totales por tienda" style={{ ...tablaStyle, width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
            {COLUMNAS.map((c) => (
              <th key={c.id} style={{ ...thCompactStyle, ...stickyHeadStyle, ...(c.id === 'tienda' ? { ...stickyColStyle, zIndex: 4, top: 0 } : {}) }}>
                {c.texto}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {totales.map((t) => <Fila key={t.sucursal_id} total={t} />)}
        </tbody>
      </table>
    </MotoredTableScroll>
  );
}
