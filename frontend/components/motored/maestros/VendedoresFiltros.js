'use client';
/**
 * frontend/components/motored/maestros/VendedoresFiltros.js
 *
 * Filtros de la lista de vendedores (texto, cargo y estado). Controlado por el
 * padre; los filtros se aplican con el botón "Filtrar". Las opciones de cargo
 * son las sugeridas más los cargos libres que ya existen en la lista.
 */
import { CARGOS_SUGERIDOS, optionStyle } from './VendedorForm';

const labelStyle = { display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' };

export function opcionesDeCargo(vendedores) {
  const extras = vendedores.map((v) => v.cargo).filter((c) => c && !CARGOS_SUGERIDOS.includes(c));
  return [...CARGOS_SUGERIDOS, ...Array.from(new Set(extras)).sort()];
}

export default function VendedoresFiltros({ filtros, setFiltros, vendedores, onAplicar }) {
  const set = (campo) => (e) => setFiltros({ ...filtros, [campo]: e.target.value });
  return (
    <form
      role="search"
      onSubmit={(e) => { e.preventDefault(); onAplicar(); }}
      style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' }}
    >
      <label style={labelStyle}>
        Buscar
        <input type="text" value={filtros.q} onChange={set('q')} placeholder="Nombre o cédula" />
      </label>
      <label style={labelStyle}>
        Filtrar por cargo
        <select value={filtros.cargo} onChange={set('cargo')}>
          <option value="" style={optionStyle}>Todos los cargos</option>
          {opcionesDeCargo(vendedores).map((c) => (
            <option key={c} value={c} style={optionStyle}>{c}</option>
          ))}
        </select>
      </label>
      <label style={labelStyle}>
        Estado
        <select value={filtros.activo} onChange={set('activo')}>
          <option value="" style={optionStyle}>Todos</option>
          <option value="true" style={optionStyle}>Activos</option>
          <option value="false" style={optionStyle}>Inactivos</option>
        </select>
      </label>
      <button type="submit" className="motored-btn motored-btn-secondary">Filtrar</button>
    </form>
  );
}
