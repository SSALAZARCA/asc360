'use client';
/** Fields every launch shares (corrida or scenario): fecha de corte, nota, todas las tiendas o una selección. */
import { MODO_SELECCION, MODO_TODAS } from './useLanzarCorrida';
import { errorStyle, labelStyle, mutedStyle } from './styles';

// Tablet touch target: 44 px for every field and choice.
const radioStyle = { display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem', minHeight: '44px' };
const campoStyle = { minHeight: '44px', boxSizing: 'border-box' };

function ListaTiendas({ tiendas, seleccion, alternar }) {
  if (tiendas.error) return <p role="alert" style={errorStyle}>{tiendas.error}</p>;
  if (!tiendas.items) return <p style={mutedStyle}>Cargando tiendas...</p>;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '0.25rem 1rem', maxHeight: '220px', overflowY: 'auto' }}>
      {tiendas.items.map((s) => (
        <label key={s.id} style={radioStyle}>
          <input type="checkbox" checked={seleccion.includes(s.id)} onChange={() => alternar(s.id)} />
          {s.nombre}
        </label>
      ))}
    </div>
  );
}

export default function CamposCorrida({ lanzar: l }) {
  return (
    <>
      <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <label style={labelStyle}>
          Fecha de corte
          <input type="date" value={l.fecha} style={campoStyle} onChange={(e) => l.setFecha(e.target.value)} />
        </label>
        <label style={{ ...labelStyle, flex: '1 1 220px' }}>
          Nota (opcional)
          <input maxLength={500} value={l.nota} style={campoStyle} onChange={(e) => l.setNota(e.target.value)} />
        </label>
      </div>
      <div style={{ display: 'flex', gap: '1.25rem', flexWrap: 'wrap' }}>
        <label style={radioStyle}>
          <input type="radio" name="alcance" checked={l.modo === MODO_TODAS} onChange={() => l.setModo(MODO_TODAS)} />
          Todas las tiendas
        </label>
        <label style={radioStyle}>
          <input type="radio" name="alcance" checked={l.modo === MODO_SELECCION} onChange={() => l.setModo(MODO_SELECCION)} />
          Selección de tiendas
        </label>
      </div>
      {l.modo === MODO_SELECCION && <ListaTiendas tiendas={l.tiendas} seleccion={l.seleccion} alternar={l.alternar} />}
    </>
  );
}
