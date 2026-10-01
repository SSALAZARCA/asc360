/** Legend of the state dots of the consolidated matrix: only the states its tiendas really have. */
import { ETIQUETA_ESTADO, PuntoEstado, estadoColumna } from './ConsolidadoColumna';
import { mutedStyle } from './styles';

const ORDEN = ['BORRADOR', 'CERRADO', 'ENVIADO', 'FALLIDA', 'OMITIDA'];

export default function ConsolidadoLeyenda({ tiendas }) {
  const presentes = ORDEN.filter((estado) => tiendas.some((t) => estadoColumna(t) === estado));
  if (presentes.length === 0) return null;
  return (
    <div role="group" aria-label="Estado de cada tienda" style={{ ...mutedStyle, display: 'flex', gap: '0.25rem 1rem', flexWrap: 'wrap', alignItems: 'center' }}>
      {presentes.map((estado) => (
        <span key={estado} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
          <PuntoEstado estado={estado} oculto />
          {ETIQUETA_ESTADO[estado]}
        </span>
      ))}
    </div>
  );
}
