'use client';
/**
 * frontend/components/motored/cargas/CargaDetalle.js
 *
 * Pantalla de detalle de una carga (sdd/motored-pedidos-ingesta, Phase 10,
 * task 10.2): 3 pestañas -- Resumen / Errores / Vista previa -- y polling
 * cada 3 segundos MIENTRAS `estado` es `PROCESANDO`/`APLICANDO` (design "No
 * WebSocket/SSE exists -- polling since GET /cargas/{id} cheaply reflects
 * filas_leidas/lotes_staged/latido_en progress per already-committed
 * batches"). No hay job-queue API separada: esto ES la superficie de
 * progreso (design §API).
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { getCarga } from '../../../lib/motored/api';
import { labelTipo } from './tiposCarga';
import EstadoBadge from './EstadoBadge';
import ResumenTab from './ResumenTab';
import ErroresTab from './ErroresTab';
import VistaPreviaTab from './VistaPreviaTab';

const TABS = [
  { id: 'resumen', label: 'Resumen' },
  { id: 'errores', label: 'Errores' },
  { id: 'preview', label: 'Vista previa' },
];

const ESTADOS_EN_PROGRESO = new Set(['PROCESANDO', 'APLICANDO']);
export const POLL_INTERVALO_MS = 3000;

function useCargaPolling(cargaId) {
  const [carga, setCarga] = useState(null);
  const [error, setError] = useState('');
  const timerRef = useRef(null);

  const cargar = useCallback(async () => {
    try {
      const data = await getCarga(cargaId);
      setCarga(data);
      setError('');
      return data;
    } catch (err) {
      setError(err.message || 'No se pudo cargar la carga');
      return null;
    }
  }, [cargaId]);

  useEffect(() => {
    let cancelado = false;

    const tick = async () => {
      const data = await cargar();
      if (cancelado) return;
      if (data && ESTADOS_EN_PROGRESO.has(data.estado)) {
        timerRef.current = setTimeout(tick, POLL_INTERVALO_MS);
      }
    };

    tick();

    return () => {
      cancelado = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [cargar]);

  return { carga, error, reload: cargar };
}

export default function CargaDetalle({ cargaId }) {
  const { carga, error, reload } = useCargaPolling(cargaId);
  const [activeTab, setActiveTab] = useState('resumen');

  if (error) return <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.85rem' }}>{error}</p>;
  if (!carga) return <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.85rem' }}>Cargando...</p>;

  const enProgreso = ESTADOS_EN_PROGRESO.has(carga.estado);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <h1 className="motored-h-pantalla">{labelTipo(carga.tipo)} — {carga.nombre_archivo}</h1>
          <EstadoBadge estado={carga.estado} />
        </div>
        {enProgreso && (
          <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' }} data-testid="carga-en-progreso">
            Procesando… {carga.filas_leidas} fila(s) leídas hasta ahora. Esta pantalla se actualiza sola cada 3 segundos.
          </p>
        )}
      </div>

      <div className="motored-tab-bar">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`motored-tab${tab.id === activeTab ? ' is-active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'resumen' && <ResumenTab carga={carga} onChanged={reload} />}
      {activeTab === 'errores' && <ErroresTab carga={carga} />}
      {activeTab === 'preview' && <VistaPreviaTab carga={carga} />}
    </div>
  );
}
