'use client';
import { useState, useRef } from 'react';
import { X, FileSpreadsheet, Upload, CheckCircle, AlertCircle, Package, Bike } from 'lucide-react';

const API = () => (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace('http://', 'https://');

const inputStyle = {
  padding: '9px 12px', borderRadius: '8px',
  background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
  color: '#fff', fontSize: '12px', outline: 'none', width: '100%', boxSizing: 'border-box',
};

export default function NuevoPedidoModal({ isOpen, onClose, onSuccess }) {
  const [tipo, setTipo] = useState(null);       // 'sp' | 'motos'
  const [file, setFile] = useState(null);
  const [reference, setReference] = useState('');
  const [cycle, setCycle] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const inputRef = useRef();

  if (!isOpen) return null;

  const reset = () => {
    setTipo(null); setFile(null); setReference('');
    setCycle(''); setLoading(false); setResult(null); setError(null);
  };

  const handleClose = () => { reset(); onClose(); };

  const handleFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!f.name.endsWith('.xlsx')) { setError('Solo se aceptan archivos .xlsx'); return; }
    setFile(f); setError(null);
  };

  const handleSubmit = async () => {
    if (!file) { setError('Seleccioná el archivo Excel'); return; }
    if (tipo === 'sp' && !reference.trim()) { setError('Ingresá una referencia interna para identificar este pedido'); return; }

    setLoading(true); setError(null);
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('um_token') : null;
      const formData = new FormData();
      formData.append('file', file);

      let url;
      if (tipo === 'sp') {
        url = `${API()}/imports/new-order-sp?reference=${encodeURIComponent(reference.trim())}`;
      } else {
        url = `${API()}/imports/new-order-motos${cycle ? `?cycle=${cycle}` : ''}`;
      }

      const res = await fetch(url, {
        method: 'POST', body: formData,
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      });

      const rawText = await res.text();
      let data;
      try { data = JSON.parse(rawText); } catch { data = { detail: rawText }; }
      if (!res.ok) {
        const detail = typeof data.detail === 'string'
          ? data.detail : (data.detail?.detail ?? JSON.stringify(data.detail ?? data));
        throw new Error(detail);
      }
      setResult(data);
      if (onSuccess) onSuccess();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px',
    }}>
      <div style={{
        background: '#13131a', border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '16px', padding: '28px', width: '480px', maxWidth: '100%',
        display: 'flex', flexDirection: 'column', gap: '20px',
      }}>

        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ color: '#fff', fontWeight: 800, fontSize: '15px', margin: 0 }}>
            Nuevo Pedido
          </h3>
          <button onClick={handleClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#606075' }}>
            <X size={18} />
          </button>
        </div>

        {/* Resultado */}
        {result && (
          <div style={{ background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)', borderRadius: '10px', padding: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
              <CheckCircle size={16} style={{ color: '#22c55e' }} />
              <span style={{ color: '#22c55e', fontWeight: 700, fontSize: '12px' }}>PEDIDO CREADO</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px' }}>
              {[
                { label: 'Creados', value: result.inserted ?? 0, color: '#22c55e' },
                { label: 'Actualizados', value: result.updated ?? 0, color: '#60a5fa' },
                { label: 'Omitidos', value: result.skipped ?? 0, color: '#606075' },
              ].map(({ label, value, color }) => (
                <div key={label} style={{ textAlign: 'center' }}>
                  <p style={{ color, fontWeight: 800, fontSize: '22px', margin: 0 }}>{value}</p>
                  <p style={{ color: '#606075', fontSize: '10px', margin: 0, fontWeight: 600 }}>{label}</p>
                </div>
              ))}
            </div>
            {result.reference && (
              <p style={{ color: '#9ca3af', fontSize: '11px', marginTop: '10px', margin: '10px 0 0' }}>
                Referencia: <strong style={{ color: '#fff' }}>{result.reference}</strong>
              </p>
            )}
            {result.errors?.length > 0 && (
              <p style={{ color: '#f87171', fontSize: '11px', marginTop: '8px' }}>
                {result.errors.length} fila(s) con errores
              </p>
            )}
          </div>
        )}

        {!result && (
          <>
            {/* Paso 1: Elegir tipo */}
            {!tipo && (
              <>
                <p style={{ color: '#606075', fontSize: '11px', margin: 0 }}>
                  ¿Qué tipo de pedido querés crear?
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <button
                    onClick={() => setTipo('sp')}
                    style={{
                      padding: '20px 16px', borderRadius: '12px',
                      border: '1px solid rgba(96,165,250,0.3)',
                      background: 'rgba(96,165,250,0.06)', cursor: 'pointer',
                      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px',
                    }}
                  >
                    <Package size={28} style={{ color: '#60a5fa' }} />
                    <span style={{ color: '#fff', fontWeight: 700, fontSize: '12px' }}>Repuestos</span>
                    <span style={{ color: '#606075', fontSize: '10px', textAlign: 'center' }}>
                      Código parte, nombre, cantidad, moto que aplica
                    </span>
                  </button>
                  <button
                    onClick={() => setTipo('motos')}
                    style={{
                      padding: '20px 16px', borderRadius: '12px',
                      border: '1px solid rgba(255,95,51,0.3)',
                      background: 'rgba(255,95,51,0.06)', cursor: 'pointer',
                      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px',
                    }}
                  >
                    <Bike size={28} style={{ color: '#ff5f33' }} />
                    <span style={{ color: '#fff', fontWeight: 700, fontSize: '12px' }}>Motos</span>
                    <span style={{ color: '#606075', fontSize: '10px', textAlign: 'center' }}>
                      Referencia de moto y cantidad a solicitar
                    </span>
                  </button>
                </div>
              </>
            )}

            {/* Paso 2: Datos + Excel */}
            {tipo && (
              <>
                {/* Breadcrumb */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <button
                    onClick={() => { setTipo(null); setFile(null); setError(null); }}
                    style={{ background: 'none', border: 'none', color: '#606075', cursor: 'pointer', fontSize: '11px', padding: 0 }}
                  >
                    ← Cambiar tipo
                  </button>
                  <span style={{
                    fontSize: '10px', fontWeight: 700, padding: '2px 8px', borderRadius: '20px',
                    background: tipo === 'sp' ? 'rgba(96,165,250,0.1)' : 'rgba(255,95,51,0.1)',
                    color: tipo === 'sp' ? '#60a5fa' : '#ff5f33',
                  }}>
                    {tipo === 'sp' ? 'REPUESTOS' : 'MOTOS'}
                  </span>
                </div>

                {/* Referencia (solo SP) */}
                {tipo === 'sp' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '10px', fontWeight: 700, color: '#606075', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                      Referencia Interna <span style={{ color: '#ff5f33' }}>*</span>
                    </label>
                    <input
                      value={reference}
                      onChange={e => setReference(e.target.value)}
                      style={inputStyle}
                      placeholder="Ej: SP-2025-001 (después lo actualizás con el PI del proveedor)"
                    />
                  </div>
                )}

                {/* Ciclo (solo motos) */}
                {tipo === 'motos' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '10px', fontWeight: 700, color: '#606075', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                      Ciclo (opcional)
                    </label>
                    <input
                      type="number"
                      value={cycle}
                      onChange={e => setCycle(e.target.value)}
                      style={inputStyle}
                      placeholder="Ej: 26"
                    />
                  </div>
                )}

                {/* Columnas esperadas */}
                <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: '8px', padding: '12px' }}>
                  <p style={{ color: '#606075', fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', margin: '0 0 6px', letterSpacing: '0.06em' }}>
                    Columnas del Excel
                  </p>
                  {tipo === 'sp' ? (
                    <p style={{ color: '#9ca3af', fontSize: '11px', margin: 0, lineHeight: 1.8 }}>
                      <span style={{ color: '#ff5f33' }}>Codigo Parte</span> &nbsp;|&nbsp;
                      <span style={{ color: '#ff5f33' }}>Cantidad</span> &nbsp;|&nbsp;
                      Nombre &nbsp;|&nbsp; Moto Aplica
                    </p>
                  ) : (
                    <p style={{ color: '#9ca3af', fontSize: '11px', margin: 0, lineHeight: 1.8 }}>
                      <span style={{ color: '#ff5f33' }}>Referencia</span> &nbsp;|&nbsp;
                      <span style={{ color: '#ff5f33' }}>Cantidad</span> &nbsp;|&nbsp;
                      Descripcion
                    </p>
                  )}
                  <p style={{ color: '#404050', fontSize: '10px', margin: '6px 0 0' }}>
                    Las columnas en naranja son obligatorias
                  </p>
                </div>

                {/* Drop zone */}
                <div
                  onClick={() => inputRef.current?.click()}
                  style={{
                    border: `2px dashed ${file ? 'rgba(34,197,94,0.4)' : 'rgba(255,95,51,0.3)'}`,
                    borderRadius: '12px', padding: '28px', textAlign: 'center', cursor: 'pointer',
                    background: file ? 'rgba(34,197,94,0.04)' : 'transparent',
                  }}
                >
                  <input ref={inputRef} type="file" accept=".xlsx" onChange={handleFile} style={{ display: 'none' }} />
                  <FileSpreadsheet size={28} style={{ color: file ? '#22c55e' : '#ff5f33', margin: '0 auto 10px' }} />
                  {file
                    ? <p style={{ color: '#22c55e', fontWeight: 600, fontSize: '12px', margin: 0 }}>{file.name}</p>
                    : <>
                        <p style={{ color: '#fff', fontWeight: 600, fontSize: '12px', margin: '0 0 4px' }}>Seleccioná el archivo Excel</p>
                        <p style={{ color: '#606075', fontSize: '10px', margin: 0 }}>Solo archivos .xlsx</p>
                      </>
                  }
                </div>
              </>
            )}
          </>
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
          {tipo && !result && (
            <button
              onClick={handleSubmit}
              disabled={!file || loading}
              style={{
                display: 'flex', alignItems: 'center', gap: '6px',
                padding: '8px 20px', borderRadius: '8px', border: 'none',
                background: file && !loading ? '#ff5f33' : 'rgba(255,95,51,0.3)',
                color: '#fff', cursor: file && !loading ? 'pointer' : 'not-allowed',
                fontSize: '12px', fontWeight: 700,
              }}
            >
              <Upload size={13} />
              {loading ? 'Procesando...' : 'Crear Pedido'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
