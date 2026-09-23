'use client';
/**
 * frontend/components/motored/cargas/VistaPreviaTab.js
 *
 * `GET /cargas/{id}/preview` (sdd/motored-pedidos-ingesta, Phase 10, task
 * 10.2) -- hasta 200 filas normalizadas de `carga_fila_staging`, ya
 * scopeadas por sucursal server-side para el rol `SUCURSAL` (ver
 * `_filtrar_staging_por_sucursal` en `backend/app/motored/api/cargas.py`):
 * este componente NO repite ese filtro, confía en lo que el backend ya
 * devuelve.
 *
 * Estructura de tabla calcada de `maestros/BulkUploadModal.js::FilasPreview`
 * (columnas dinámicas a partir de las claves de la primera fila).
 */
import { useEffect, useState } from 'react';
import { getPreviewCarga } from '../../../lib/motored/api';

function usePreview(cargaId) {
  const [filas, setFilas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getPreviewCarga(cargaId)
      .then((data) => { if (!cancelled) setFilas(data); })
      .catch((err) => { if (!cancelled) setError(err.message || 'No se pudo cargar la vista previa'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [cargaId]);

  return { filas, loading, error };
}

export default function VistaPreviaTab({ carga }) {
  const { filas, loading, error } = usePreview(carga.id);

  if (error) return <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{error}</p>;
  if (loading) return <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>Cargando...</p>;
  if (filas.length === 0) {
    return <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>Sin filas para mostrar todavía.</p>;
  }

  const columnasPayload = Object.keys(filas[0].payload || {});

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Mostrando hasta 200 filas normalizadas de este archivo.
      </p>
      <div style={{ maxHeight: '480px', overflow: 'auto', border: '1px solid var(--motored-border, #e4e4e7)', borderRadius: '6px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.75rem' }} data-testid="preview-grid">
          <thead>
            <tr style={{ background: 'var(--motored-surface-alt, #f4f4f5)' }}>
              <th style={{ textAlign: 'left', padding: '0.4rem 0.6rem' }}>Fila</th>
              {columnasPayload.map((c) => (
                <th key={c} style={{ textAlign: 'left', padding: '0.4rem 0.6rem' }}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filas.map((fila) => (
              <tr key={fila.fila} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
                <td style={{ padding: '0.4rem 0.6rem' }} className="motored-mono">{fila.fila}</td>
                {columnasPayload.map((c) => (
                  <td key={c} style={{ padding: '0.4rem 0.6rem' }}>{String(fila.payload?.[c] ?? '')}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
