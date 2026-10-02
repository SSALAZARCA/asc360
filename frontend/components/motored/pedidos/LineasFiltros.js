'use client';
/** Controlled filters of the line table: class, stock state, search, edited only, excluded. */
import { ESTADOS_QUIEBRE } from './formato';
import { labelStyle, optionStyle, touchStyle } from './styles';

const CLASES = ['AF', 'AM', 'AS', 'BF', 'BM', 'BS', 'CF', 'CM', 'CS', 'DS'];
const checkStyle = { display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.8rem', minHeight: '44px' };

function Selector({ label, valor, opciones, onChange }) {
  return (
    <label style={labelStyle}>
      {label}
      <select value={valor} style={touchStyle} onChange={(e) => onChange(e.target.value)}>
        <option value="" style={optionStyle}>Todas</option>
        {opciones.map(([v, texto]) => <option key={v} value={v} style={optionStyle}>{texto}</option>)}
      </select>
    </label>
  );
}

function Casilla({ texto, marcada, onChange }) {
  return (
    <label style={checkStyle}>
      <input type="checkbox" checked={marcada} onChange={(e) => onChange(e.target.checked)} />
      {texto}
    </label>
  );
}

export default function LineasFiltros({ filters, setFilter }) {
  return (
    <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
      <Selector label="Clase" valor={filters.clase} opciones={CLASES.map((c) => [c, c])} onChange={(v) => setFilter('clase', v)} />
      <Selector label="Quiebre" valor={filters.estado_quiebre} opciones={ESTADOS_QUIEBRE} onChange={(v) => setFilter('estado_quiebre', v)} />
      <label style={labelStyle}>
        Buscar
        <input type="search" value={filters.q} style={touchStyle} placeholder="Código o nombre" onChange={(e) => setFilter('q', e.target.value)} />
      </label>
      <Casilla texto="Solo editadas" marcada={filters.solo_editadas} onChange={(v) => setFilter('solo_editadas', v)} />
      <Casilla texto="Mostrar excluidas" marcada={filters.incluir_excluidas} onChange={(v) => setFilter('incluir_excluidas', v)} />
    </div>
  );
}
