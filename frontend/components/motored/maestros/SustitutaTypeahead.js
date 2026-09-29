'use client';
/**
 * frontend/components/motored/maestros/SustitutaTypeahead.js
 *
 * Type-ahead for "Código de referencia sustituta" (`odd/tasks/motored-
 * referencias-paginacion.md`). Replaces the old `<select>` that listed every
 * referencia of the proveedor: it searches the server
 * (`buscarSustitutas`, same proveedor, excluding the row being edited, max
 * 20 results) as the user types.
 *
 * Controlled by the parent through `value = { id, codigo }`: typing sets
 * `{ id: '', codigo: text }` (free text is never sent as a sustituta),
 * choosing an option sets both. The same-proveedor rule is also enforced
 * server-side on save.
 */
import { useEffect, useRef, useState } from 'react';
import { buscarSustitutas } from '../../../lib/motored/api';
import useDebouncedValue from '../../../lib/motored/useDebouncedValue';
import InfoTooltip from '../InfoTooltip';

const LIST_ID = 'sustituta-opciones';
const labelStyle = { display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' };
const listStyle = {
  position: 'absolute', zIndex: 10, margin: 0, padding: 0, listStyle: 'none', minWidth: '100%',
  maxHeight: '14rem', overflowY: 'auto', background: '#ffffff', border: '1px solid var(--motored-border, #e4e4e7)',
};
const optionStyle = { color: '#1a1a18', padding: '0.35rem 0.5rem', cursor: 'pointer', fontSize: '0.75rem' };

function useSustitutas(proveedorId, excludeId, texto) {
  const [resultados, setResultados] = useState([]);
  const q = useDebouncedValue(texto.trim(), 300);
  useEffect(() => {
    if (!proveedorId || !q) {
      setResultados([]);
      return undefined;
    }
    let vigente = true;
    buscarSustitutas({ proveedorId, q, excludeId: excludeId || null })
      .then((res) => vigente && setResultados(res))
      .catch(() => vigente && setResultados([]));
    return () => { vigente = false; };
  }, [proveedorId, excludeId, q]);
  return resultados;
}

function Opciones({ listRef, resultados, onSelect }) {
  return (
    <ul id={LIST_ID} role="listbox" ref={listRef} style={listStyle}>
      {resultados.map((r) => (
        <li key={r.id} role="option" aria-selected={false} tabIndex={-1} style={optionStyle} onClick={() => onSelect(r)}>
          {r.codigo}{r.nombre ? ` — ${r.nombre}` : ''}
        </li>
      ))}
    </ul>
  );
}

export default function SustitutaTypeahead({ proveedorId, excludeId, value, onChange, help }) {
  const [abierto, setAbierto] = useState(false);
  const listRef = useRef(null);
  const resultados = useSustitutas(proveedorId, excludeId, abierto ? value.codigo : '');
  const visible = abierto && resultados.length > 0;
  const select = (r) => {
    onChange({ id: r.id, codigo: r.codigo });
    setAbierto(false);
  };
  const onBlur = (e) => {
    if (!listRef.current || !listRef.current.contains(e.relatedTarget)) setAbierto(false);
  };

  return (
    <div style={{ position: 'relative' }}>
      <label style={labelStyle}>
        <span>
          Código de referencia sustituta
          <InfoTooltip text={help} />
        </span>
        <input
          role="combobox" aria-autocomplete="list" aria-expanded={visible} aria-controls={LIST_ID}
          value={value.codigo} disabled={!proveedorId} placeholder="Buscar por código o nombre"
          onChange={(e) => { setAbierto(true); onChange({ id: '', codigo: e.target.value }); }}
          onKeyDown={(e) => e.key === 'Escape' && setAbierto(false)}
          onBlur={onBlur}
        />
      </label>
      {visible && <Opciones listRef={listRef} resultados={resultados} onSelect={select} />}
    </div>
  );
}
