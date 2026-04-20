'use client';
import { useState, useRef } from 'react';
import { authFetch } from '../../lib/authFetch';
import { X, Upload, FileSpreadsheet, CheckCircle, AlertCircle } from 'lucide-react';

export default function ExcelUploadModal({ isOpen, onClose, onSuccess, uploadUrl, title = 'Importar Excel' }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const inputRef = useRef();

  if (!isOpen) return null;

  const handleFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!f.name.endsWith('.xlsx')) {
      setError('Solo se aceptan archivos .xlsx');
      return;
    }
    setFile(f);
    setError(null);
    setResult(null);
  };

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const token = typeof window !== 'undefined' ? sessionStorage.getItem('um_token') : null;
      const formData = new FormData();
      formData.append('file', file);
      // Fetch directo — NO usar authFetch para evitar que inyecte Content-Type: application/json
      // que rompe el boundary de multipart/form-data y causa 422 en FastAPI.
      const res = await fetch(uploadUrl, {
        method: 'POST',
        body: formData,
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      });
      const rawText = await res.text();
      let data;
      try { data = JSON.parse(rawText); } catch { data = { detail: rawText }; }
      if (!res.ok) {
        const detail = typeof data.detail === 'string'
          ? data.detail
          : JSON.stringify(data.detail ?? data);
        throw new Error(detail);
      }
      setResult(data);
      if (onSuccess) onSuccess(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setFile(null);
    setResult(null);
    setError(null);
    onClose();
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: '#13131a', border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '16px', padding: '28px', width: '440px', maxWidth: '90vw',
        display: 'flex', flexDirection: 'column', gap: '20px',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ color: '#fff', fontWeight: 700, fontSize: '15px', margin: 0 }}>{title}</h3>
          <button onClick={handleClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#606075', padding: '4px' }}>
            <X size={18} />
          </button>
        </div>

        {/* Drop zone */}
        {!result && (
          <div
            onClick={() => inputRef.current?.click()}
            style={{
              border: '2px dashed rgba(255,95,51,0.3)', borderRadius: '12px',
              padding: '32px', textAlign: 'center', cursor: 'pointer',
              background: file ? 'rgba(255,95,51,0.05)' : 'transparent',
              transition: 'all 0.2s',
            }}
          >
            <input ref={inputRef} type="file" accept=".xlsx" onChange={handleFile} style={{ display: 'none' }} />
            <FileSpreadsheet size={32} style={{ color: '#ff5f33', margin: '0 auto 12px' }} />
            {file ? (
              <p style={{ color: '#fff', fontWeight: 600, fontSize: '13px', margin: 0 }}>{file.name}</p>
            ) : (
              <>
                <p style={{ color: '#fff', fontWeight: 600, fontSize: '13px', margin: '0 0 4px' }}>Seleccioná un archivo Excel</p>
                <p style={{ color: '#606075', fontSize: '11px', margin: 0 }}>Solo archivos .xlsx</p>
              </>
            )}
          </div>
        )}

        {/* Resultado */}
        {result && (
          <div style={{ background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)', borderRadius: '10px', padding: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
              <CheckCircle size={16} style={{ color: '#22c55e' }} />
              <span style={{ color: '#22c55e', fontWeight: 700, fontSize: '12px' }}>IMPORTACIÓN COMPLETADA</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px' }}>
              {[
                { label: 'Creados', value: result.inserted ?? result.result?.moto_units_added ?? 0, color: '#22c55e' },
                { label: 'Actualizados', value: result.updated ?? result.result?.moto_units_updated ?? result.result?.sp_items_updated ?? 0, color: '#60a5fa' },
                { label: 'Sin cambios', value: result.skipped ?? 0, color: '#606075' },
              ].map(({ label, value, color }) => (
                <div key={label} style={{ textAlign: 'center' }}>
                  <p style={{ color, fontWeight: 800, fontSize: '20px', margin: 0 }}>{value}</p>
                  <p style={{ color: '#606075', fontSize: '10px', margin: 0, fontWeight: 600 }}>{label}</p>
                </div>
              ))}
            </div>
            {result.errors?.length > 0 && (
              <p style={{ color: '#f87171', fontSize: '11px', marginTop: '10px', margin: '10px 0 0' }}>
                {result.errors.length} fila(s) con errores
              </p>
            )}
            {result.result?.duplicates_skipped?.length > 0 && (
              <div style={{ marginTop: '12px', background: 'rgba(251,191,36,0.06)', border: '1px solid rgba(251,191,36,0.2)', borderRadius: '8px', padding: '10px' }}>
                <p style={{ color: '#fbbf24', fontWeight: 700, fontSize: '11px', margin: '0 0 6px' }}>
                  ⚠ {result.result.duplicates_skipped.length} VIN(s) omitidos por duplicado
                </p>
                <div style={{ maxHeight: '100px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '3px' }}>
                  {result.result.duplicates_skipped.map((d, i) => (
                    <p key={i} style={{ color: '#fbbf24', fontSize: '10px', margin: 0, opacity: 0.85 }}>
                      Fila {d.row}: <strong>{d.vin}</strong> — {d.reason}
                    </p>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', borderRadius: '8px', padding: '12px' }}>
            <AlertCircle size={14} style={{ color: '#f87171', flexShrink: 0 }} />
            <span style={{ color: '#f87171', fontSize: '12px' }}>{error}</span>
          </div>
        )}

        {/* Acciones */}
        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
          <button onClick={handleClose} style={{
            padding: '8px 16px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)',
            background: 'transparent', color: '#606075', cursor: 'pointer', fontSize: '12px', fontWeight: 600,
          }}>
            {result ? 'Cerrar' : 'Cancelar'}
          </button>
          {!result && (
            <button
              onClick={handleUpload}
              disabled={!file || loading}
              style={{
                padding: '8px 20px', borderRadius: '8px', border: 'none',
                background: file && !loading ? '#ff5f33' : 'rgba(255,95,51,0.3)',
                color: '#fff', cursor: file && !loading ? 'pointer' : 'not-allowed',
                fontSize: '12px', fontWeight: 700,
                display: 'flex', alignItems: 'center', gap: '6px',
              }}
            >
              <Upload size={13} />
              {loading ? 'Procesando...' : 'Importar'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
