'use client';
/** Controlled filters of the corridas list: calculation state, kind, pedido stage. */
import { labelStyle, optionStyle } from './styles';

const ESTADOS = [
  ['', 'Todos'], ['PENDIENTE', 'Pendiente'], ['CALCULANDO', 'Calculando'],
  ['BORRADOR', 'Calculada'], ['FALLIDA', 'Fallida'], ['ANULADA', 'Anulada'],
];
const TIPOS = [['', 'Todas'], ['false', 'Reales'], ['true', 'Pruebas']];
const PEDIDOS = [
  ['', 'Todos'], ['abiertos', 'Con tiendas en borrador'],
  ['por_enviar', 'Con tiendas cerradas por enviar'], ['enviados', 'Ya enviadas'],
];

function Selector({ label, valor, opciones, onChange }) {
  return (
    <label style={labelStyle}>
      {label}
      <select value={valor} onChange={(e) => onChange(e.target.value)}>
        {opciones.map(([v, texto]) => <option key={v} value={v} style={optionStyle}>{texto}</option>)}
      </select>
    </label>
  );
}

export default function CorridasFiltros({ filters, setFilter }) {
  return (
    <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
      <Selector label="Estado" valor={filters.estado} opciones={ESTADOS} onChange={(v) => setFilter('estado', v)} />
      <Selector label="Tipo" valor={filters.escenario} opciones={TIPOS} onChange={(v) => setFilter('escenario', v)} />
      <Selector label="Pedidos" valor={filters.pedidos} opciones={PEDIDOS} onChange={(v) => setFilter('pedidos', v)} />
    </div>
  );
}
