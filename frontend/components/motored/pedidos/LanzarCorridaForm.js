'use client';
/** "Nueva corrida" form: fecha de corte, todas las tiendas o una selección, nota. */
import { MODO_SELECCION, MODO_TODAS } from './useLanzarCorrida';
import { cardStyle, errorStyle, labelStyle, mutedStyle } from './styles';

const radioStyle = { display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem' };

function ListaTiendas({ tiendas, seleccion, alternar }) {
  if (tiendas.error) return <p role="alert" style={errorStyle}>{tiendas.error}</p>;
  if (!tiendas.items) return <p style={mutedStyle}>Cargando tiendas...</p>;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '0.25rem 1rem', maxHeight: '220px', overflowY: 'auto' }}>
      {tiendas.items.map((s) => (
        <label key={s.id} style={{ ...radioStyle, minHeight: '36px' }}>
          <input type="checkbox" checked={seleccion.includes(s.id)} onChange={() => alternar(s.id)} />
          {s.nombre}
        </label>
      ))}
    </div>
  );
}

export default function LanzarCorridaForm({ lanzar: l }) {
  return (
    <form
      aria-label="Nueva corrida" style={cardStyle}
      onSubmit={(e) => { e.preventDefault(); if (l.listo) l.lanzar(); }}
    >
      <h2 className="motored-h-seccion">Nueva corrida</h2>
      <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <label style={labelStyle}>
          Fecha de corte
          <input type="date" value={l.fecha} onChange={(e) => l.setFecha(e.target.value)} />
        </label>
        <label style={{ ...labelStyle, flex: '1 1 220px' }}>
          Nota (opcional)
          <input maxLength={500} value={l.nota} onChange={(e) => l.setNota(e.target.value)} />
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
      {l.error && <p role="alert" style={errorStyle}>{l.error}</p>}
      {l.creada && <p role="status" style={mutedStyle}>{`Corrida ${l.creada.codigo} creada: se está calculando.`}</p>}
      <div>
        <button type="submit" className="motored-btn motored-btn-primary" disabled={!l.listo}>Calcular corrida</button>
      </div>
    </form>
  );
}
