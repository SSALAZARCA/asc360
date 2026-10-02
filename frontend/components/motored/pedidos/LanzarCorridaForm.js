'use client';
/** "Nueva corrida" form: fecha de corte, todas las tiendas o una selección, nota. */
import CamposCorrida from './CamposCorrida';
import { cardStyle, errorStyle, mutedStyle, touchStyle } from './styles';

export default function LanzarCorridaForm({ lanzar: l }) {
  return (
    <form
      aria-label="Nueva corrida" style={cardStyle}
      onSubmit={(e) => { e.preventDefault(); if (l.listo) l.lanzar(); }}
    >
      <h2 className="motored-h-seccion">Nueva corrida</h2>
      <CamposCorrida lanzar={l} />
      {l.error && <p role="alert" style={errorStyle}>{l.error}</p>}
      {l.creada && <p role="status" style={mutedStyle}>{`Corrida ${l.creada.codigo} creada: se está calculando.`}</p>}
      <div>
        <button type="submit" className="motored-btn motored-btn-primary" style={touchStyle} disabled={!l.listo}>Calcular corrida</button>
      </div>
    </form>
  );
}
