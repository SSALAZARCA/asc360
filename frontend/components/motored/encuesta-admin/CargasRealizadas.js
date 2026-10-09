'use client';
/** Presentational table of past customer-base uploads. */
import { Fragment, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import MotoredTableScroll from '../MotoredTableScroll';
import { descargarExcelCargaEncuesta } from '../../../lib/motored/encuestaCargasApi';
import DetalleCarga from './DetalleCarga';
import DescargarResultados from './DescargarResultados';
import { fechaHoraBogota } from '../../../lib/motored/fechas';
import { cardStyle, errorStyle } from './styles';

const thStyle = { padding: '0 12px 8px 0', textAlign: 'left' };
const tdStyle = { padding: '10px 12px 10px 0' };

function respondidas(carga) {
  const pct = carga.total_registros ? Math.round((carga.respondidos / carga.total_registros) * 100) : 0;
  return `${carga.respondidos} (${pct}%)`;
}

const iconBtn = {
  background: 'none', border: 'none', cursor: 'pointer', padding: '2px', color: 'inherit', display: 'inline-flex',
};

export default function CargasRealizadas({ cargas, loading, error }) {
  const [abiertas, setAbiertas] = useState({});
  const [descargando, setDescargando] = useState(null);
  const [errorExcel, setErrorExcel] = useState('');

  const alternar = (id) => setAbiertas((prev) => ({ ...prev, [id]: !prev[id] }));
  const bajarExcel = async (carga) => {
    setDescargando(carga.id);
    setErrorExcel('');
    try {
      await descargarExcelCargaEncuesta(carga.id, carga.nombre_archivo);
    } catch (err) {
      setErrorExcel(err.message || 'No se pudo descargar el Excel.');
    } finally {
      setDescargando(null);
    }
  };

  return (
    <section style={cardStyle}>
      <h2 className="motored-h-seccion">Cargas realizadas</h2>
      <DescargarResultados />
      {errorExcel && <div role="alert" style={errorStyle}>{errorExcel}</div>}
      {error && <div role="alert" style={errorStyle}>{error}</div>}
      {!error && loading && <p style={{ margin: 0, fontSize: '0.8rem' }}>Cargando...</p>}
      {!error && !loading && cargas.length === 0 && (
        <p style={{ margin: 0, fontSize: '0.8rem' }}>Todavía no hay cargas de clientes.</p>
      )}
      {!error && cargas.length > 0 && (
        <MotoredTableScroll>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
                <th style={thStyle}><span style={{ position: 'absolute', left: '-9999px' }}>Detalle</span></th>
                <th style={thStyle}>Archivo</th>
                <th style={thStyle}>Fecha</th>
                <th style={thStyle}>Cargado por</th>
                <th style={thStyle}>Registros</th>
                <th style={thStyle}>Respondidas</th>
                <th style={thStyle}><span style={{ position: 'absolute', left: '-9999px' }}>Descargar</span></th>
              </tr>
            </thead>
            <tbody>
              {cargas.map((c) => {
                const abierta = Boolean(abiertas[c.id]);
                const Icono = abierta ? ChevronDown : ChevronRight;
                return (
                  <Fragment key={c.id}>
                    <tr style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
                      <td style={tdStyle}>
                        <button
                          type="button"
                          style={iconBtn}
                          aria-expanded={abierta}
                          aria-label={`Ver detalle de ${c.nombre_archivo}`}
                          onClick={() => alternar(c.id)}
                        >
                          <Icono size={16} />
                        </button>
                      </td>
                      <td style={tdStyle}>{c.nombre_archivo}</td>
                      <td style={tdStyle}>{fechaHoraBogota(c.created_at)}</td>
                      <td style={tdStyle}>{c.usuario || '—'}</td>
                      <td style={tdStyle}>{c.total_registros}</td>
                      <td style={tdStyle}>{respondidas(c)}</td>
                      <td style={tdStyle}>
                        <button
                          type="button"
                          className="motored-btn"
                          disabled={descargando === c.id}
                          aria-label={`Descargar Excel de ${c.nombre_archivo}`}
                          onClick={() => bajarExcel(c)}
                        >
                          Excel
                        </button>
                      </td>
                    </tr>
                    {abierta && (
                      <tr>
                        <td />
                        <td colSpan={6}><DetalleCarga carga={c} /></td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </MotoredTableScroll>
      )}
    </section>
  );
}
