'use client';
import { useState } from 'react';
import { authFetch } from '../../lib/authFetch';
import { getApiUrl } from '../../lib/api';
import { FileSpreadsheet, X, Download } from 'lucide-react';

export default function RemisionesExportModal({ onClose }) {
  const today = new Date().toISOString().slice(0, 10);
  const firstOfMonth = today.slice(0, 8) + '01';

  const [desde, setDesde] = useState(firstOfMonth);
  const [hasta, setHasta] = useState(today);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [dateError, setDateError] = useState('');

  const validate = () => {
    if (!desde || !hasta) {
      setDateError('Ambas fechas son requeridas');
      return false;
    }
    if (desde > hasta) {
      setDateError('La fecha de inicio debe ser anterior o igual a la fecha de fin');
      return false;
    }
    setDateError('');
    return true;
  };

  const handleDownload = async () => {
    if (!validate()) return;

    setLoading(true);
    setError('');
    try {
      const res = await authFetch(
        `${getApiUrl()}/remisiones/export?date_from=${desde}&date_to=${hasta}`
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Error ${res.status}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `remisiones-${desde}_${hasta}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      onClose();
    } catch (err) {
      setError(err.message || 'Error generando el Excel');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.65)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{
        background: '#1a1a24',
        borderRadius: '12px',
        padding: '28px',
        width: '380px',
        boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
        border: '1px solid rgba(255,255,255,0.07)',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
          <FileSpreadsheet size={18} color="#ff5f33" />
          <span style={{ fontSize: '14px', fontWeight: 700, color: '#fff' }}>
            Descargar Remisiones (Excel)
          </span>
          <button
            onClick={onClose}
            style={{
              marginLeft: 'auto', background: 'none', border: 'none',
              cursor: 'pointer', color: '#606075', padding: '2px',
            }}
          >
            <X size={16} />
          </button>
        </div>

        <p style={{ fontSize: '11px', color: '#9ca3b8', marginBottom: '20px', lineHeight: '1.5' }}>
          Genera un Excel con una fila por ítem despachado, para el rango de fechas seleccionado.
        </p>

        {/* Date inputs */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '16px' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
            <span style={{ fontSize: '10px', fontWeight: 600, color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Fecha desde
            </span>
            <input
              type="date"
              value={desde}
              onChange={(e) => { setDesde(e.target.value); setDateError(''); }}
              style={{
                padding: '8px 12px', borderRadius: '8px',
                background: 'rgba(255,255,255,0.05)',
                border: dateError ? '1px solid #f87171' : '1px solid rgba(255,255,255,0.1)',
                color: '#fff', fontSize: '13px', outline: 'none',
                colorScheme: 'dark',
              }}
            />
          </label>

          <label style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
            <span style={{ fontSize: '10px', fontWeight: 600, color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Fecha hasta
            </span>
            <input
              type="date"
              value={hasta}
              onChange={(e) => { setHasta(e.target.value); setDateError(''); }}
              style={{
                padding: '8px 12px', borderRadius: '8px',
                background: 'rgba(255,255,255,0.05)',
                border: dateError ? '1px solid #f87171' : '1px solid rgba(255,255,255,0.1)',
                color: '#fff', fontSize: '13px', outline: 'none',
                colorScheme: 'dark',
              }}
            />
          </label>
        </div>

        {/* Validation error */}
        {dateError && (
          <p style={{ fontSize: '11px', color: '#f87171', marginBottom: '12px' }}>
            {dateError}
          </p>
        )}

        {/* API error */}
        {error && (
          <p style={{ fontSize: '11px', color: '#f87171', marginBottom: '12px' }}>
            {error}
          </p>
        )}

        {/* Actions */}
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            disabled={loading}
            style={{
              padding: '9px 16px', borderRadius: '8px',
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid rgba(255,255,255,0.08)',
              color: '#9ca3b8', fontSize: '12px', cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            Cancelar
          </button>

          <button
            onClick={handleDownload}
            disabled={loading}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '9px 18px', borderRadius: '8px', border: 'none',
              background: loading ? 'rgba(255,95,51,0.4)' : '#ff5f33',
              color: '#fff', fontSize: '12px', fontWeight: 700,
              cursor: loading ? 'not-allowed' : 'pointer',
              letterSpacing: '0.03em',
            }}
          >
            <Download size={13} />
            {loading ? 'Generando...' : 'Descargar Excel'}
          </button>
        </div>
      </div>
    </div>
  );
}
