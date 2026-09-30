'use client';
/** Controlled filters bar: result, email text and date range (Colombia days). */
import { labelStyle, optionStyle } from '../detractores/styles';
import { RESULTADO_LABELS } from './labels';

export default function IngresosFilters({ filters, setFilter }) {
  const bind = (key) => ({ value: filters[key], onChange: (e) => setFilter(key, e.target.value) });
  return (
    <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
      <label style={labelStyle}>
        Resultado
        <select {...bind('resultado')}>
          <option value="" style={optionStyle}>Todos</option>
          {Object.entries(RESULTADO_LABELS).map(([value, label]) => (
            <option key={value} value={value} style={optionStyle}>{label}</option>
          ))}
        </select>
      </label>
      <label style={{ ...labelStyle, flex: '1 1 220px' }}>
        Correo contiene
        <input placeholder="ana@" {...bind('texto')} />
      </label>
      <label style={labelStyle}>
        Desde
        <input type="date" {...bind('desde')} />
      </label>
      <label style={labelStyle}>
        Hasta
        <input type="date" {...bind('hasta')} />
      </label>
    </div>
  );
}
