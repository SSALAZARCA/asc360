'use client';
import { useState, useRef } from 'react';
import AdminLayout from '../admin-layout';
import { authFetch } from '../../lib/authFetch';
import { Upload, CheckCircle2, XCircle, Loader2, BookOpen, FileText, Trash2 } from 'lucide-react';

export default function PartsCatalogPage() {
  const [modelCode, setModelCode]       = useState('');
  const [vehicleModel, setVehicleModel] = useState('');
  const [files, setFiles]               = useState([]);
  const [results, setResults]           = useState([]);
  const [loading, setLoading]           = useState(false);
  const [progress, setProgress]         = useState({ done: 0, total: 0 });
  const fileRef = useRef();

  const handleFiles = (e) => {
    const selected = Array.from(e.target.files).filter(f => f.name.endsWith('.pdf'));
    setFiles(selected);
    setResults([]);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const dropped = Array.from(e.dataTransfer.files).filter(f => f.name.endsWith('.pdf'));
    setFiles(dropped);
    setResults([]);
  };

  const removeFile = (idx) => setFiles(f => f.filter((_, i) => i !== idx));

  const handleUpload = async () => {
    if (!modelCode.trim() || !vehicleModel.trim() || files.length === 0) return;

    setLoading(true);
    setResults([]);
    setProgress({ done: 0, total: files.length });

    const newResults = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const fd = new FormData();
      fd.append('pdf_file', file);
      fd.append('model_code', modelCode.trim());
      fd.append('vehicle_model', vehicleModel.trim());

      try {
        const res = await authFetch('/parts/admin/load-section', { method: 'POST', body: fd });
        if (res.ok) {
          const data = await res.json();
          newResults.push({ filename: file.name, status: 'ok', ...data });
        } else {
          const err = await res.json().catch(() => ({ detail: 'Error desconocido' }));
          newResults.push({ filename: file.name, status: 'error', error: err.detail });
        }
      } catch (e) {
        newResults.push({ filename: file.name, status: 'error', error: e.message });
      }

      setProgress({ done: i + 1, total: files.length });
      setResults([...newResults]);
    }

    setLoading(false);
  };

  const totalParts    = results.filter(r => r.status === 'ok').reduce((s, r) => s + (r.parts_loaded || 0), 0);
  const totalRefs     = results.filter(r => r.status === 'ok').reduce((s, r) => s + (r.references_new || 0), 0);
  const successCount  = results.filter(r => r.status === 'ok').length;
  const errorCount    = results.filter(r => r.status === 'error').length;
  const pct           = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0;

  return (
    <AdminLayout>
      <div style={{ maxWidth: '860px', margin: '0 auto', padding: '2rem 1.5rem' }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '2rem' }}>
          <div style={{ width: '44px', height: '44px', borderRadius: '14px', background: 'rgba(255,95,51,0.12)', border: '1px solid rgba(255,95,51,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <BookOpen size={20} color="#ff5f33" />
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 900, color: '#fff', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Catálogo de Partes
            </h1>
            <p style={{ margin: 0, fontSize: '0.7rem', color: '#606075', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Cargá los PDFs del manual de despiece por modelo
            </p>
          </div>
        </div>

        {/* Form */}
        <div className="glass" style={{ borderRadius: '16px', padding: '1.5rem', marginBottom: '1.5rem' }}>
          <p style={{ margin: '0 0 1.25rem', fontSize: '0.7rem', fontWeight: 700, color: '#606075', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Información del modelo
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.65rem', fontWeight: 700, color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '0.5rem' }}>
                Código interno del modelo *
              </label>
              <input
                value={modelCode}
                onChange={e => setModelCode(e.target.value)}
                placeholder="ej: renegade_200_sport"
                disabled={loading}
                style={inputStyle}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.65rem', fontWeight: 700, color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '0.5rem' }}>
                Modelo del vehículo en sistema *
              </label>
              <input
                value={vehicleModel}
                onChange={e => setVehicleModel(e.target.value)}
                placeholder="ej: Renegade Sport 200S"
                disabled={loading}
                style={inputStyle}
              />
            </div>
          </div>
          <p style={{ margin: '0.75rem 0 0', fontSize: '0.65rem', color: '#404055' }}>
            El "modelo del vehículo" debe coincidir exactamente con el campo <code style={{ color: '#ff5f33' }}>vehicle.model</code> en la base de datos.
          </p>
        </div>

        {/* Drop zone */}
        <div
          className="glass"
          onDragOver={e => e.preventDefault()}
          onDrop={handleDrop}
          onClick={() => !loading && fileRef.current?.click()}
          style={{ borderRadius: '16px', padding: '2rem', marginBottom: '1.5rem', border: '2px dashed rgba(255,255,255,0.08)', textAlign: 'center', cursor: loading ? 'default' : 'pointer', transition: 'border-color 0.2s' }}
          onMouseEnter={e => { if (!loading) e.currentTarget.style.borderColor = 'rgba(255,95,51,0.3)'; }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)'; }}
        >
          <Upload size={28} color="#606075" style={{ marginBottom: '0.75rem' }} />
          <p style={{ margin: '0 0 0.25rem', fontSize: '0.8rem', fontWeight: 700, color: '#fff' }}>
            Arrastrá los PDFs acá o hacé click para seleccionar
          </p>
          <p style={{ margin: 0, fontSize: '0.65rem', color: '#606075' }}>
            Podés seleccionar múltiples archivos · Solo archivos .pdf
          </p>
          <input ref={fileRef} type="file" multiple accept=".pdf" onChange={handleFiles} style={{ display: 'none' }} />
        </div>

        {/* File list */}
        {files.length > 0 && (
          <div className="glass" style={{ borderRadius: '16px', padding: '1.25rem', marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <p style={{ margin: 0, fontSize: '0.7rem', fontWeight: 700, color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                {files.length} archivo{files.length !== 1 ? 's' : ''} seleccionado{files.length !== 1 ? 's' : ''}
              </p>
              {!loading && (
                <button onClick={() => { setFiles([]); setResults([]); }} style={{ background: 'none', border: 'none', color: '#606075', cursor: 'pointer', fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Limpiar todo
                </button>
              )}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '220px', overflowY: 'auto' }}>
              {files.map((f, i) => {
                const result = results.find(r => r.filename === f.name);
                return (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.625rem 0.875rem', borderRadius: '10px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <FileText size={14} color={result?.status === 'ok' ? '#10b981' : result?.status === 'error' ? '#ef4444' : '#606075'} />
                    <span style={{ flex: 1, fontSize: '0.72rem', color: '#ccc', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {f.name}
                    </span>
                    {result?.status === 'ok' && (
                      <span style={{ fontSize: '0.6rem', color: '#10b981', fontWeight: 700, whiteSpace: 'nowrap' }}>
                        ✓ {result.parts_loaded} repuestos
                      </span>
                    )}
                    {result?.status === 'error' && (
                      <span style={{ fontSize: '0.6rem', color: '#ef4444', fontWeight: 700, whiteSpace: 'nowrap', maxWidth: '160px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        ✗ {result.error}
                      </span>
                    )}
                    {!result && loading && progress.done > i && (
                      <Loader2 size={13} color="#ff5f33" style={{ animation: 'spin 1s linear infinite' }} />
                    )}
                    {!result && !loading && (
                      <button onClick={() => removeFile(i)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#404055', padding: '2px', display: 'flex' }}>
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Progress bar */}
        {loading && (
          <div className="glass" style={{ borderRadius: '12px', padding: '1.25rem', marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.625rem' }}>
              <span style={{ fontSize: '0.7rem', fontWeight: 700, color: '#fff' }}>
                Procesando {progress.done} de {progress.total} archivos...
              </span>
              <span style={{ fontSize: '0.7rem', fontWeight: 700, color: '#ff5f33' }}>{pct}%</span>
            </div>
            <div style={{ height: '6px', borderRadius: '99px', background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${pct}%`, borderRadius: '99px', background: 'linear-gradient(90deg, #ff5f33, #ff8c69)', transition: 'width 0.3s ease' }} />
            </div>
          </div>
        )}

        {/* Action button */}
        <button
          onClick={handleUpload}
          disabled={loading || !modelCode.trim() || !vehicleModel.trim() || files.length === 0}
          style={{
            width: '100%', padding: '0.9rem', borderRadius: '12px', border: 'none', cursor: loading || !modelCode.trim() || !vehicleModel.trim() || files.length === 0 ? 'not-allowed' : 'pointer',
            background: loading || !modelCode.trim() || !vehicleModel.trim() || files.length === 0 ? 'rgba(255,95,51,0.2)' : '#ff5f33',
            color: '#fff', fontWeight: 900, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.08em',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem',
            transition: 'background 0.2s', marginBottom: '1.5rem',
          }}
        >
          {loading ? <><Loader2 size={15} style={{ animation: 'spin 1s linear infinite' }} /> Cargando...</> : <><Upload size={15} /> Cargar {files.length > 0 ? `${files.length} archivo${files.length !== 1 ? 's' : ''}` : 'archivos'}</>}
        </button>

        {/* Summary */}
        {results.length > 0 && !loading && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
            {[
              { label: 'Secciones cargadas', value: successCount, color: '#10b981' },
              { label: 'Referencias nuevas', value: totalRefs, color: '#ff5f33' },
              { label: 'Repuestos en diagrama', value: totalParts, color: '#6366f1' },
              ...(errorCount > 0 ? [{ label: 'Con errores', value: errorCount, color: '#ef4444' }] : []),
            ].map((s, i) => (
              <div key={i} className="glass" style={{ borderRadius: '12px', padding: '1.25rem', textAlign: 'center' }}>
                <p style={{ margin: '0 0 0.25rem', fontSize: '1.6rem', fontWeight: 900, color: s.color }}>{s.value}</p>
                <p style={{ margin: 0, fontSize: '0.6rem', fontWeight: 700, color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{s.label}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <style jsx global>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </AdminLayout>
  );
}

const inputStyle = {
  width: '100%',
  padding: '0.75rem 1rem',
  background: 'rgba(255,255,255,0.04)',
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: '10px',
  color: '#fff',
  fontSize: '0.8rem',
  outline: 'none',
  boxSizing: 'border-box',
};
