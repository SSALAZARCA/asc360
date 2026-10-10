'use client';
/**
 * frontend/components/motored/maestros/DescargarReferenciasExcel.js
 *
 * "Descargar Excel" button of the Referencias tab (`odd/tasks/motored-
 * referencias-descarga-excel.md`). It downloads what the table is showing
 * filtered: `consulta` is the same (debounced) query `buscarReferencias`
 * uses, and only its filters are sent -- never the page -- so the file
 * holds every matching referencia, or the whole master without filters.
 */
import { useState } from 'react';
import { descargarReferenciasExcel } from '../../../lib/motored/api';

const errorStyle = { margin: 0, color: 'var(--motored-danger, #c0392b)', fontSize: '0.75rem' };

export default function DescargarReferenciasExcel({ consulta }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const descargar = async () => {
    setBusy(true);
    setError('');
    try {
      const { q, lineaComercial, activa } = consulta;
      await descargarReferenciasExcel({ q, lineaComercial, activa });
    } catch (err) {
      setError(`No se pudo descargar el Excel (${err.message || 'error desconocido'}).`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
      <button
        type="button"
        className="motored-btn motored-btn-secondary"
        onClick={descargar}
        disabled={busy}
        aria-busy={busy}
        style={{ whiteSpace: 'nowrap' }}
      >
        {busy ? 'Descargando…' : 'Descargar Excel'}
      </button>
      {error && <p role="alert" style={errorStyle}>{error}</p>}
    </div>
  );
}
