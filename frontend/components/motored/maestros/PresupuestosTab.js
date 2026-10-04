'use client';
/**
 * frontend/components/motored/maestros/PresupuestosTab.js
 *
 * Maestros > Presupuestos (odd/motored-presupuestos-gerencia, T3): monthly sales
 * budget per asesor, for ADMIN and GERENCIA. Month selector, the month grouped by
 * tienda with totals, Excel upload (dry-run first), manual edit/add/remove and
 * the version history. Every upload or manual change creates a new version.
 *
 * The store options come from `GET /presupuestos/tiendas` (GERENCIA cannot read
 * `/maestros/sucursales`), plus the stores already present in the month.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  getMesPresupuesto, guardarAsesorPresupuesto, listarMesesPresupuesto, listarTiendasPresupuesto,
  quitarAsesorPresupuesto,
} from '../../../lib/motored/presupuestosApi';
import MesPresupuesto from './presupuestos/MesPresupuesto';
import EditorAsesor from './presupuestos/EditorAsesor';
import HistorialVersiones from './presupuestos/HistorialVersiones';
import CargaPresupuestosModal from './presupuestos/CargaPresupuestosModal';
import { labelStyle, optionStyle, panelStyle, errorStyle, mutedStyle, mesLegible } from './presupuestos/formato';

export default function PresupuestosTab() {
  const [meses, setMeses] = useState(null);
  const [mesActual, setMesActual] = useState(null);
  const [detalle, setDetalle] = useState(null);
  const [tiendas, setTiendas] = useState([]);
  const [editor, setEditor] = useState(null); // { modo, linea? }
  const [historial, setHistorial] = useState(false);
  const [subiendo, setSubiendo] = useState(false);
  const [aviso, setAviso] = useState(null);
  const [error, setError] = useState(null);
  const mesSolicitado = useRef(null); // latest month asked for: older responses are ignored

  const cargarMeses = useCallback(async (preferido) => {
    try {
      const lista = await listarMesesPresupuesto();
      setMeses(lista);
      setError(null);
      setMesActual((actual) => {
        const buscado = preferido || actual;
        return lista.some((m) => m.mes === buscado) ? buscado : (lista[0]?.mes ?? null);
      });
    } catch (e) {
      setMeses([]);
      setError(e.message || 'No se pudieron cargar los presupuestos.');
    }
  }, []);

  useEffect(() => { cargarMeses(); }, [cargarMeses]);
  useEffect(() => {
    listarTiendasPresupuesto().then(setTiendas).catch(() => setTiendas([]));
  }, []);

  const cargarDetalle = useCallback(async (mes) => {
    mesSolicitado.current = mes;
    try {
      const respuesta = await getMesPresupuesto(mes);
      if (mesSolicitado.current !== mes) return;
      setDetalle(respuesta);
      setError(null);
    } catch (e) {
      if (mesSolicitado.current !== mes) return;
      setError(e.message || 'No se pudo cargar el mes.');
    }
  }, []);

  useEffect(() => {
    setEditor(null);
    setHistorial(false);
    setDetalle(null);
    setError(null);
    mesSolicitado.current = mesActual;
    if (mesActual) cargarDetalle(mesActual);
  }, [mesActual, cargarDetalle]);

  const opcionesTienda = useMemo(() => {
    const porId = new Map(tiendas.map((t) => [t.id, t]));
    (detalle?.por_tienda || []).forEach((t) => {
      if (!porId.has(t.sucursal_id)) porId.set(t.sucursal_id, { id: t.sucursal_id, nombre: t.tienda });
    });
    return [...porId.values()];
  }, [tiendas, detalle]);

  const tras = async (version) => {
    setEditor(null);
    setAviso(`Se creó la versión ${version.version} de ${version.mes}.`);
    await Promise.all([cargarDetalle(mesActual), cargarMeses(mesActual)]);
  };

  const guardar = async ({ cedula, sucursal_id: sucursalId, monto, nota }) => {
    const cuerpo = { sucursal_id: sucursalId, monto, ...(nota ? { nota } : {}) };
    await tras(await guardarAsesorPresupuesto(mesActual, cedula, cuerpo));
  };
  const quitar = async ({ cedula, nota }) => {
    await tras(await quitarAsesorPresupuesto(mesActual, cedula, nota));
  };

  const alAplicar = async (respuesta) => {
    setAviso(respuesta.meses.map((m) => `${m.mes}: versión ${m.version}`).join(' · '));
    const aplicado = respuesta.meses[0]?.mes;
    await cargarMeses(aplicado);
    // The month effect only reruns when the selection changes; refresh in place otherwise.
    if (aplicado && aplicado === mesActual) await cargarDetalle(aplicado);
  };

  if (meses === null) return <p style={mutedStyle}>Cargando presupuestos…</p>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', minWidth: 0 }}>
      <div style={{ ...panelStyle, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <div>
          <h2 className="motored-h-seccion">Presupuestos</h2>
          <p style={mutedStyle}>Presupuesto mensual de ventas por asesor. Cada cambio crea una nueva versión del mes.</p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          {meses.length > 0 && (
            <label style={labelStyle} htmlFor="presupuesto-mes">
              Mes
              <select id="presupuesto-mes" value={mesActual || ''} onChange={(e) => setMesActual(e.target.value)}>
                {meses.map((m) => (
                  <option key={m.mes} value={m.mes} style={optionStyle}>{mesLegible(m.mes)} (v{m.version})</option>
                ))}
              </select>
            </label>
          )}
          <button type="button" className="motored-btn motored-btn-primary" onClick={() => setSubiendo(true)}>
            Cargar presupuestos
          </button>
        </div>
      </div>

      {error && <p role="alert" style={errorStyle}>{error}</p>}
      {aviso && <p role="status" style={{ ...mutedStyle, color: 'var(--motored-success, #15803d)' }}>{aviso}</p>}

      {meses.length === 0 ? (
        <div style={panelStyle}>
          <strong>Aún no hay presupuestos cargados</strong>
          <p style={mutedStyle}>Carga un archivo de Excel con la cédula, el mes, la tienda y el presupuesto de cada asesor.</p>
          <div>
            <button type="button" className="motored-btn motored-btn-primary" onClick={() => setSubiendo(true)}>
              Cargar presupuestos
            </button>
          </div>
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <button type="button" className="motored-btn motored-btn-secondary"
              disabled={!mesActual} onClick={() => setEditor({ modo: 'agregar' })}>Agregar asesor</button>
            <button type="button" className="motored-btn motored-btn-secondary"
              disabled={!mesActual} onClick={() => setHistorial((v) => !v)}>Historial de versiones</button>
          </div>
          {editor && (
            <EditorAsesor
              key={`${editor.modo}-${editor.linea?.cedula || 'nuevo'}`}
              modo={editor.modo}
              linea={editor.linea}
              tiendas={opcionesTienda}
              onGuardar={editor.modo === 'quitar' ? quitar : guardar}
              onCancelar={() => setEditor(null)}
            />
          )}
          {detalle && (
            <MesPresupuesto
              detalle={detalle}
              onEditar={(linea) => setEditor({ modo: 'editar', linea })}
              onQuitar={(linea) => setEditor({ modo: 'quitar', linea })}
            />
          )}
          {historial && <HistorialVersiones mes={mesActual} />}
        </>
      )}

      {subiendo && (
        <CargaPresupuestosModal onAplicado={alAplicar} onClose={() => setSubiendo(false)} />
      )}
    </div>
  );
}
