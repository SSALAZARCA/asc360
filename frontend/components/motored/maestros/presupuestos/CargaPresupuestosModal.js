'use client';
/**
 * Upload of budgets from Excel: template, dry-run summary per month, errors
 * that block the apply, and the apply itself. Dedicated to budgets (the generic
 * BulkUploadModal does not fit: one file can carry several months and each one
 * becomes a new version).
 */
import { useState } from 'react';
import { formatCOP } from '../../../../lib/motored/formatCOP';
import {
  aplicarPresupuestos, descargarPlantillaPresupuestos, validarPresupuestos,
} from '../../../../lib/motored/presupuestosApi';
import MotoredTableScroll from '../../MotoredTableScroll';
import InfoTooltip from '../../InfoTooltip';
import {
  panelStyle, tablaStyle, thStyle, tdStyle, filaStyle, errorStyle, mutedStyle, mesLegible,
} from './formato';

const overlayStyle = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', padding: '1rem',
  display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200,
};
const boxStyle = {
  background: 'var(--motored-surface, #ffffff)', border: '1px solid var(--motored-border, #e4e4e7)',
  borderRadius: 'var(--motored-radius-md, 8px)', padding: '1.25rem', width: '100%', maxWidth: '760px',
  maxHeight: '90vh', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem',
  boxSizing: 'border-box',
};

function TablaIncidencias({ titulo, filas }) {
  if (!filas.length) return null;
  return (
    <div>
      <strong style={{ fontSize: '0.8rem' }}>{titulo} ({filas.length})</strong>
      <MotoredTableScroll maxHeight="14rem">
        <table style={tablaStyle}>
          <thead>
            <tr style={{ textAlign: 'left', color: 'var(--motored-text-muted, #5a5a5a)' }}>
              {['Fila', 'Columna', 'Mensaje'].map((t) => <th key={t} style={thStyle}>{t}</th>)}
            </tr>
          </thead>
          <tbody>
            {filas.map((f, i) => (
              <tr key={`${f.fila}-${f.columna}-${i}`} style={filaStyle}>
                <td style={tdStyle}>{f.fila}</td>
                <td style={tdStyle}>{f.columna}</td>
                <td style={tdStyle}>{f.mensaje}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </MotoredTableScroll>
    </div>
  );
}

function ResumenMes({ mes }) {
  return (
    <section aria-label={`Mes ${mes.mes}`} style={panelStyle}>
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'baseline' }}>
        <strong>{mesLegible(mes.mes)} ({mes.mes})</strong>
        <span>{mes.asesores} asesores · {formatCOP(mes.total)}</span>
        <span style={mutedStyle}>
          {mes.reemplaza_version ? `reemplaza la versión ${mes.reemplaza_version}` : 'mes nuevo'}
          <InfoTooltip text="Si el mes ya tiene presupuesto, el archivo crea una versión nueva que lo sustituye por completo; la anterior queda en el historial. Un asesor que no aparece en el archivo queda sin presupuesto ese mes." />
        </span>
      </div>
      <MotoredTableScroll>
        <table style={tablaStyle}>
          <thead>
            <tr style={{ textAlign: 'left', color: 'var(--motored-text-muted, #5a5a5a)' }}>
              {['Tienda', 'Asesores', 'Total'].map((t) => <th key={t} style={thStyle}>{t}</th>)}
            </tr>
          </thead>
          <tbody>
            {mes.por_tienda.map((t) => (
              <tr key={t.sucursal_id} style={filaStyle}>
                <td style={tdStyle}>{t.tienda}</td>
                <td style={tdStyle}>{t.asesores}</td>
                <td style={tdStyle}>{formatCOP(t.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </MotoredTableScroll>
    </section>
  );
}

export default function CargaPresupuestosModal({ onAplicado, onClose }) {
  const [archivo, setArchivo] = useState(null);
  const [resumen, setResumen] = useState(null);
  const [resultado, setResultado] = useState(null);
  const [errores, setErrores] = useState([]);
  const [error, setError] = useState(null);
  const [ocupado, setOcupado] = useState(false);

  const elegir = (evento) => {
    setArchivo(evento.target.files?.[0] || null);
    setResumen(null);
    setErrores([]);
    setError(null);
  };

  const ejecutar = async (accion) => {
    setOcupado(true);
    setError(null);
    setErrores([]);
    try {
      await accion();
    } catch (e) {
      setError(e.message || 'No se pudo completar la acción.');
      setErrores(e.errores || []);
    } finally {
      setOcupado(false);
    }
  };

  const descargarPlantilla = async () => {
    try {
      await descargarPlantillaPresupuestos();
    } catch (e) {
      setError(e.message || 'No se pudo descargar la plantilla.');
    }
  };

  const validar = () => ejecutar(async () => setResumen(await validarPresupuestos(archivo)));
  const aplicar = () => ejecutar(async () => {
    const respuesta = await aplicarPresupuestos(archivo);
    setResultado(respuesta);
    onAplicado(respuesta);
  });

  return (
    <div role="dialog" aria-label="Cargar presupuestos" style={overlayStyle}>
      <div style={boxStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap' }}>
          <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 800 }}>Cargar presupuestos</h2>
          <button type="button" className="motored-btn motored-btn-tertiary"
            onClick={descargarPlantilla}>
            Descargar plantilla Excel
          </button>
        </div>
        <p style={mutedStyle}>
          Columnas: Año (4 dígitos, ej. 2026), Mes (número de 1 a 12), Cédula, Tienda (C.O. o nombre) y Presupuesto.
          El archivo puede traer uno o varios meses; cada mes reemplaza solo a ese mes y crea una versión
          nueva. El formato anterior también sigue funcionando: sin la columna Año, una sola columna Mes
          con la fecha completa (AAAA-MM o MM/AAAA).
        </p>
        {!resultado && (
          <>
            <input type="file" accept=".xlsx" aria-label="Archivo de presupuestos" onChange={elegir} />
            {error && <p role="alert" style={errorStyle}>{error}</p>}
            <TablaIncidencias titulo="Errores" filas={errores.length ? errores : (resumen?.errores || [])} />
            {resumen && resumen.meses.map((m) => <ResumenMes key={m.mes} mes={m} />)}
            {resumen && <TablaIncidencias titulo="Advertencias" filas={resumen.warnings} />}
          </>
        )}
        {resultado && (
          <section aria-label="Resultado de la carga" style={panelStyle}>
            <strong>Presupuestos aplicados</strong>
            <ul style={{ margin: 0, paddingLeft: '1.1rem', fontSize: '0.85rem' }}>
              {resultado.meses.map((m) => (
                <li key={m.mes}>{m.mes}: versión {m.version} ({m.asesores} asesores, {formatCOP(m.total)})</li>
              ))}
            </ul>
          </section>
        )}
        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
          <button type="button" className="motored-btn motored-btn-secondary" onClick={onClose}>
            {resultado ? 'Cerrar' : 'Cancelar'}
          </button>
          {!resultado && (
            <>
              <button type="button" className="motored-btn motored-btn-secondary"
                disabled={!archivo || ocupado} onClick={validar}>Validar</button>
              <button type="button" className="motored-btn motored-btn-primary"
                disabled={!resumen?.valido || ocupado} onClick={aplicar}>Aplicar</button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
