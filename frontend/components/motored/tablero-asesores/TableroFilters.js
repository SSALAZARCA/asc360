'use client';
/** Controlled filters: first month, last month and HMCL mode. */
const labelStyle = { display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)', gap: '2px' };
// Dark-theme rule: every <option> needs an explicit colour.
const optionStyle = { color: '#1a1a18' };

const MODOS_HMCL = [
  ['incluir', 'Incluir HMCL'],
  ['excluir', 'Excluir HMCL'],
  ['solo', 'Solo HMCL'],
];

export default function TableroFilters({ filtros, setFiltros }) {
  const cambiar = (campo) => (e) => setFiltros({ ...filtros, [campo]: e.target.value });
  return (
    <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
      <label style={labelStyle}>
        Mes desde
        <input type="month" value={filtros.desde} onChange={cambiar('desde')} />
      </label>
      <label style={labelStyle}>
        Mes hasta
        <input type="month" value={filtros.hasta} onChange={cambiar('hasta')} />
      </label>
      <label style={labelStyle}>
        HMCL
        <select value={filtros.hmcl} onChange={cambiar('hmcl')}>
          {MODOS_HMCL.map(([valor, texto]) => <option key={valor} value={valor} style={optionStyle}>{texto}</option>)}
        </select>
      </label>
    </div>
  );
}
