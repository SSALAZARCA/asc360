'use client';
import { useState, useRef, useEffect } from 'react';
import AdminLayout from '../admin-layout';
import { authFetch } from '../../lib/authFetch';
import { Upload, Loader2, BookOpen, FileText, Trash2, ChevronDown } from 'lucide-react';

export default function PartsCatalogPage() {
  const [vehicleModels, setVehicleModels] = useState([]);
  const [loadingModels, setLoadingModels]  = useState(true);

  const [vehicleModel, setVehicleModel] = useState('');
  const [modelCode, setModelCode]       = useState('');
  const [codeAutoFilled, setCodeAutoFilled] = useState(false);

  const [files, setFiles]     = useState([]);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const fileRef = useRef();

  useEffect(() => {
    authFetch('/parts/admin/vehicle-models')
      .then(r => r.ok ? r.json() : [])
      .then(data => { setVehicleModels(Array.isArray(data) ? data : []); })
      .catch(() => {})
      .finally(() => setLoadingModels(false));
  }, []);

  const handleVehicleModelChange = (value) => {
    setVehicleModel(value);
    setResults([]);
    const match = vehicleModels.find(m => m.vehicle_model === value);
    if (match?.catalog_model_code) {
      setModelCode(match.catalog_model_code);
      setCodeAutoFilled(true);
    } else {
      setModelCode('');
      setCodeAutoFilled(false);
    }
  };

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
    if (!modelCode.trim() || !vehicleModel || files.length === 0) return;
    setLoading(true);
    setResults([]);
    setProgress({ done: 0, total: files.length });

    const newResults = [];
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const fd = new FormData();
      fd.append('pdf_file', file);
      fd.append('model_code', modelCode.trim());
      fd.append('vehicle_model', vehicleModel);

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

  const totalParts   = results.filter(r => r.status === 'ok').reduce((s, r) => s + (r.parts_loaded || 0), 0);
  const totalRefs    = results.filter(r => r.status === 'ok').reduce((s, r) => s + (r.references_new || 0), 0);
  const successCount = results.filter(r => r.status === 'ok').length;
  const errorCount   = results.filter(r => r.status === 'error').length;
  const pct          = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0;
  const canUpload    = !loading && modelCode.trim() && vehicleModel && files.length > 0;

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

            {/* Dropdown o input de modelo del vehículo */}
            <div>
              <label style={labelStyle}>
                Modelo del vehículo *
                {!loadingModels && vehicleModels.length === 0 && (
                  <span style={{ marginLeft: '0.5rem', fontSize: '0.55rem', color: '#f59e0b', fontWeight: 700 }}>MANUAL</span>
                )}
              </label>
              {loadingModels ? (
                <input disabled placeholder="Cargando modelos..." style={{ ...inputStyle, opacity: 0.5 }} />
              ) : vehicleModels.length > 0 ? (
                <div style={{ position: 'relative' }}>
                  <select
                    value={vehicleModel}
                    onChange={e => handleVehicleModelChange(e.target.value)}
                    disabled={loading}
                    style={{ ...inputStyle, appearance: 'none', paddingRight: '2.5rem', cursor: 'pointer' }}
                  >
                    <option value="">— Seleccioná un modelo —</option>
                    {vehicleModels.map(m => (
                      <option key={m.vehicle_model} value={m.vehicle_model}>
                        {m.vehicle_model}{m.catalog_model_code ? ' ✓' : ''}
                      </option>
                    ))}
                  </select>
                  <ChevronDown size={14} color="#606075" style={{ position: 'absolute', right: '0.875rem', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
                </div>
              ) : (
                <input
                  value={vehicleModel}
                  onChange={e => handleVehicleModelChange(e.target.value)}
                  placeholder="Ej: Renegade Sport 200S"
                  disabled={loading}
                  style={inputStyle}
                />
              )}
              {vehicleModel && (
                <p style={{ margin: '0.4rem 0 0', fontSize: '0.6rem', color: '#606075' }}>
                  {vehicleModels.find(m => m.vehicle_model === vehicleModel)?.catalog_model_code
                    ? '✓ Ya tiene catálogo — se reemplazarán las secciones que subas'
                    : '⚡ Modelo nuevo — se creará el catálogo'}
                </p>
              )}
            </div>

            {/* Código interno del modelo */}
            <div>
              <label style={labelStyle}>
                Código interno del modelo *
                {codeAutoFilled && (
                  <span style={{ marginLeft: '0.5rem', fontSize: '0.55rem', color: '#10b981', fontWeight: 700 }}>AUTO</span>
                )}
              </label>
              <input
                value={modelCode}
                onChange={e => { setModelCode(e.target.value); setCodeAutoFilled(false); }}
                placeholder="ej: renegade_200_sport"
                disabled={loading}
                style={inputStyle}
              />
              <p style={{ margin: '0.4rem 0 0', fontSize: '0.6rem', color: '#606075' }}>
                {codeAutoFilled
                  ? 'Completado automáticamente desde el catálogo existente'
                  : 'Usá minúsculas y guiones bajos. Ej: renegade_200_sport'}
              </p>
            </div>
          </div>
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
                const isProcessing = loading && !result && progress.done <= i;
                return (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.625rem 0.875rem', borderRadius: '10px', background: 'rgba(255,255,255,0.03)', border: `1px solid ${result?.status === 'ok' ? 'rgba(16,185,129,0.15)' : result?.status === 'error' ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.05)'}` }}>
                    <FileText size={14} color={result?.status === 'ok' ? '#10b981' : result?.status === 'error' ? '#ef4444' : '#606075'} />
                    <span style={{ flex: 1, fontSize: '0.72rem', color: '#ccc', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {f.name}
                    </span>
                    {result?.status === 'ok' && (
                      <span style={{ fontSize: '0.6rem', color: '#10b981', fontWeight: 700, whiteSpace: 'nowrap' }}>
                        ✓ {result.parts_loaded} repuestos · {result.references_new} refs nuevas
                      </span>
                    )}
                    {result?.status === 'error' && (
                      <span style={{ fontSize: '0.6rem', color: '#ef4444', fontWeight: 700, whiteSpace: 'nowrap', maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        ✗ {result.error}
                      </span>
                    )}
                    {isProcessing && (
                      <Loader2 size={13} color="#ff5f33" style={{ animation: 'spin 1s linear infinite', flexShrink: 0 }} />
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

        {/* Botón */}
        <button
          onClick={handleUpload}
          disabled={!canUpload}
          style={{
            width: '100%', padding: '0.9rem', borderRadius: '12px', border: 'none',
            cursor: canUpload ? 'pointer' : 'not-allowed',
            background: canUpload ? '#ff5f33' : 'rgba(255,95,51,0.2)',
            color: '#fff', fontWeight: 900, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.08em',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem',
            transition: 'background 0.2s', marginBottom: '1.5rem',
          }}
        >
          {loading
            ? <><Loader2 size={15} style={{ animation: 'spin 1s linear infinite' }} /> Cargando...</>
            : <><Upload size={15} /> Cargar {files.length > 0 ? `${files.length} archivo${files.length !== 1 ? 's' : ''}` : 'archivos'}</>
          }
        </button>

        {/* Resumen */}
        {results.length > 0 && !loading && (
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(${errorCount > 0 ? 4 : 3}, 1fr)`, gap: '1rem' }}>
            {[
              { label: 'Secciones cargadas', value: successCount, color: '#10b981' },
              { label: 'Referencias nuevas', value: totalRefs,    color: '#ff5f33' },
              { label: 'Items en diagramas', value: totalParts,   color: '#6366f1' },
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
        select option { background: #0c0c0e; color: #fff; }
      `}</style>
    </AdminLayout>
  );
}

const labelStyle = {
  display: 'block',
  fontSize: '0.65rem',
  fontWeight: 700,
  color: '#606075',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom: '0.5rem',
};

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
