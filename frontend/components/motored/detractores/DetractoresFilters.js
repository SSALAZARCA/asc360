'use client';
/** Controlled filters bar: search, centro, consent and date range. */
import { labelStyle, optionStyle } from './styles';

export default function DetractoresFilters({ filters, setFilter }) {
  const bind = (key) => ({ value: filters[key], onChange: (e) => setFilter(key, e.target.value) });
  return (
    <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
      <label style={{ ...labelStyle, flex: '1 1 220px' }}>
        Buscar
        <input placeholder="Nombre, cédula, placa o código de caso" {...bind('q')} />
      </label>
      <label style={labelStyle}>
        Centro de servicio
        <input {...bind('centro')} />
      </label>
      <label style={labelStyle}>
        Autorizó datos
        <select {...bind('autoriza')}>
          <option value="" style={optionStyle}>Todos</option>
          <option value="true" style={optionStyle}>Sí</option>
          <option value="false" style={optionStyle}>No</option>
        </select>
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
