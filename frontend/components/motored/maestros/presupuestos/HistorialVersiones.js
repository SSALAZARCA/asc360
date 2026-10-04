'use client';
/**
 * Version history of one month (read-only): the list of versions and, when one
 * is chosen, its lines.
 */
import { useEffect, useState } from 'react';
import { formatCOP } from '../../../../lib/motored/formatCOP';
import { getVersionesPresupuesto, getVersionPresupuesto } from '../../../../lib/motored/presupuestosApi';
import MotoredTableScroll from '../../MotoredTableScroll';
import InfoTooltip from '../../InfoTooltip';
import {
  panelStyle, tablaStyle, thStyle, tdStyle, filaStyle, errorStyle, mutedStyle, origenLegible, fechaLegible,
} from './formato';

function LineasSoloLectura({ detalle }) {
  return (
    <section aria-label={`Versión ${detalle.version} (solo lectura)`} style={panelStyle}>
      <strong style={{ fontSize: '0.85rem' }}>
        Versión {detalle.version} (solo lectura) · {detalle.asesores} asesores · {formatCOP(detalle.total)}
      </strong>
      <MotoredTableScroll>
        <table style={tablaStyle}>
          <thead>
            <tr style={{ textAlign: 'left', color: 'var(--motored-text-muted, #5a5a5a)' }}>
              {['Asesor', 'Cédula', 'Tienda', 'Presupuesto'].map((t) => <th key={t} style={thStyle}>{t}</th>)}
            </tr>
          </thead>
          <tbody>
            {detalle.lineas.map((l) => (
              <tr key={l.cedula} style={filaStyle}>
                <td style={tdStyle}>{l.asesor}</td>
                <td style={tdStyle}>{l.cedula}</td>
                <td style={tdStyle}>{l.tienda}</td>
                <td style={tdStyle}>{formatCOP(l.monto)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </MotoredTableScroll>
    </section>
  );
}

export default function HistorialVersiones({ mes }) {
  const [versiones, setVersiones] = useState(null);
  const [detalle, setDetalle] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let vigente = true;
    setVersiones(null);
    setDetalle(null);
    getVersionesPresupuesto(mes)
      .then((v) => { if (vigente) setVersiones(v); })
      .catch((e) => { if (vigente) setError(e.message || 'No se pudo cargar el historial.'); });
    return () => { vigente = false; };
  }, [mes]);

  const ver = (id) => {
    setError(null);
    getVersionPresupuesto(id).then(setDetalle).catch((e) => setError(e.message || 'No se pudo cargar la versión.'));
  };

  return (
    <section aria-label="Historial de versiones del mes" style={panelStyle}>
      <strong style={{ fontSize: '0.85rem' }}>
        Historial de versiones
        <InfoTooltip text="Cada carga o cambio guardó una versión del mes. Solo se pueden consultar; los indicadores usan siempre la última." />
      </strong>
      {error && <p role="alert" style={errorStyle}>{error}</p>}
      {!versiones && !error && <p style={mutedStyle}>Cargando…</p>}
      {versiones && (
        <MotoredTableScroll>
          <table style={tablaStyle}>
            <thead>
              <tr style={{ textAlign: 'left', color: 'var(--motored-text-muted, #5a5a5a)' }}>
                {['Versión', 'Origen', 'Archivo', 'Nota', 'Fecha', 'Usuario', 'Líneas', 'Total', ''].map((t) => (
                  <th key={t || 'acc'} style={thStyle}>{t}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {versiones.map((v) => (
                <tr key={v.id} style={filaStyle}>
                  <td style={tdStyle}>{v.version}</td>
                  <td style={tdStyle}>{origenLegible(v.origen)}</td>
                  <td style={tdStyle}>{v.archivo_nombre || '—'}</td>
                  <td style={tdStyle}>{v.nota || '—'}</td>
                  <td style={tdStyle}>{fechaLegible(v.created_at)}</td>
                  <td style={tdStyle}>{v.created_by_nombre || '—'}</td>
                  <td style={tdStyle}>{v.lineas}</td>
                  <td style={tdStyle}>{formatCOP(v.total)}</td>
                  <td style={tdStyle}>
                    <button type="button" className="motored-btn motored-btn-tertiary"
                      aria-label={`Ver versión ${v.version}`} onClick={() => ver(v.id)}>Ver</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </MotoredTableScroll>
      )}
      {detalle && <LineasSoloLectura detalle={detalle} />}
    </section>
  );
}
