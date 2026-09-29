'use client';
/**
 * frontend/components/motored/maestros/ReferenciasFiltros.js
 *
 * Search box plus línea comercial / estado filters for the Referencias tab
 * (`odd/tasks/motored-referencias-paginacion.md`). Purely presentational:
 * the parent owns the values, debounces the search and resets the page.
 * `estado` is '' (todas), 'true' (activas) or 'false' (inactivas).
 */
const optionStyle = { color: '#1a1a18' };
const labelStyle = { display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' };

const ESTADOS = [
  { value: '', label: 'Todas' },
  { value: 'true', label: 'Activas' },
  { value: 'false', label: 'Inactivas' },
];

function LineaSelect({ value, lineas, onChange }) {
  return (
    <label style={labelStyle}>
      Línea comercial
      <select aria-label="Filtrar por línea comercial" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="" style={optionStyle}>Todas</option>
        {lineas.map((linea) => (
          <option key={linea} value={linea} style={optionStyle}>{linea}</option>
        ))}
      </select>
    </label>
  );
}

function EstadoSelect({ value, onChange }) {
  return (
    <label style={labelStyle}>
      Estado
      <select aria-label="Filtrar por estado" value={value} onChange={(e) => onChange(e.target.value)}>
        {ESTADOS.map((estado) => (
          <option key={estado.value} value={estado.value} style={optionStyle}>{estado.label}</option>
        ))}
      </select>
    </label>
  );
}

export default function ReferenciasFiltros({ filtros, lineas, onChange }) {
  const set = (key) => (value) => onChange({ ...filtros, [key]: value });
  return (
    <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
      <label style={labelStyle}>
        Buscar referencia
        <input
          type="search"
          value={filtros.q}
          placeholder="Código o nombre"
          onChange={(e) => set('q')(e.target.value)}
        />
      </label>
      <LineaSelect value={filtros.linea} lineas={lineas} onChange={set('linea')} />
      <EstadoSelect value={filtros.estado} onChange={set('estado')} />
    </div>
  );
}
