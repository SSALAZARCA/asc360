'use client';
/** Presentational table of the conteos list (WU11/WU12b): store, date, leader, estado and follow-up with the progress of open conteos. */
import MotoredTableScroll from '../MotoredTableScroll';
import { fechaBogota, fechaHoraBogota } from '../../../lib/motored/fechas';
import { ESTADOS_ABIERTOS, ESTADOS_CONTEO, formatEntero, porcentajeAvance } from './conteosFormato';
import EstadoConteoBadge from './EstadoConteoBadge';
import { cardStyle, labelStyle, mutedStyle, optionStyle, selectStyle, tdStyle, thStyle } from './estilos';

const ANULABLES = ['PROGRAMADO', ...ESTADOS_ABIERTOS];

function seguimiento(conteo) {
  if (conteo.cerrado_en) return `Cerrado ${fechaHoraBogota(conteo.cerrado_en)}`;
  if (conteo.anulado_en) return `Anulado ${fechaHoraBogota(conteo.anulado_en)}`;
  if (conteo.iniciado_en) return `Iniciado ${fechaHoraBogota(conteo.iniciado_en)}`;
  return 'Sin iniciar';
}

function Avance({ progreso }) {
  const pct = porcentajeAvance(progreso);
  if (pct == null) return null;
  return <div>{`Avance ${pct} % (${formatEntero(progreso.refs_contadas)} de ${formatEntero(progreso.refs_universo)})`}</div>;
}

function Acciones({ conteo, administra, onAbrir, onReprogramar, onAnular }) {
  const tienda = conteo.sucursal.nombre;
  return (
    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
      <button type="button" className="motored-btn motored-btn-secondary" aria-label={`Abrir ${tienda}`} onClick={() => onAbrir(conteo)}>
        Abrir
      </button>
      {administra && conteo.estado === 'PROGRAMADO' && (
        <button type="button" className="motored-btn motored-btn-tertiary" aria-label={`Reprogramar ${tienda}`} onClick={() => onReprogramar(conteo)}>
          Reprogramar
        </button>
      )}
      {administra && ANULABLES.includes(conteo.estado) && (
        <button type="button" className="motored-btn motored-btn-tertiary" aria-label={`Anular ${tienda}`} onClick={() => onAnular(conteo)}>
          Anular
        </button>
      )}
    </div>
  );
}

export default function ConteosLista({ conteos, cargando, estado, onEstado, administra, ...acciones }) {
  return (
    <div style={cardStyle}>
      <label style={{ ...labelStyle, maxWidth: '220px' }}>
        Estado
        <select value={estado} onChange={(e) => onEstado(e.target.value)} style={selectStyle}>
          <option value="" style={optionStyle}>Todos</option>
          {ESTADOS_CONTEO.map((e) => <option key={e.value} value={e.value} style={optionStyle}>{e.label}</option>)}
        </select>
      </label>
      {!cargando && conteos.length === 0 && <p style={{ ...mutedStyle, margin: 0 }}>No hay conteos para mostrar.</p>}
      {conteos.length > 0 && (
        <MotoredTableScroll>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
            <thead>
              <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
                <th style={thStyle}>Tienda</th>
                <th style={thStyle}>Fecha</th>
                <th style={thStyle}>Líder</th>
                <th style={thStyle}>Estado</th>
                <th style={thStyle}>Seguimiento</th>
                <th style={thStyle}>Acción</th>
              </tr>
            </thead>
            <tbody>
              {conteos.map((c) => (
                <tr key={c.id} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
                  <td style={{ ...tdStyle, fontWeight: 700 }}>{c.sucursal.nombre}</td>
                  <td style={tdStyle}>{fechaBogota(c.fecha_programada)}</td>
                  <td style={tdStyle}>{c.lider?.nombre ?? '—'}</td>
                  <td style={tdStyle}><EstadoConteoBadge estado={c.estado} /></td>
                  <td style={{ ...tdStyle, ...mutedStyle, fontSize: '0.8rem' }}>
                    <div>{seguimiento(c)}</div>
                    <Avance progreso={c.progreso} />
                  </td>
                  <td style={tdStyle}><Acciones conteo={c} administra={administra} {...acciones} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </MotoredTableScroll>
      )}
    </div>
  );
}
