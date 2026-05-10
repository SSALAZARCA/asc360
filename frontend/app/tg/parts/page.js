'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { authFetch } from '../../../lib/authFetch';
import TgNav from '../../../components/tg/TgNav';

export default function TgParts() {
  const router = useRouter();
  const [user, setUser]           = useState(null);
  const [models, setModels]       = useState([]);
  const [model, setModel]         = useState('');
  const [desc, setDesc]           = useState('');
  const [results, setResults]     = useState([]);
  const [sections, setSections]   = useState([]);
  const [loading, setLoading]     = useState(false);
  const [loadingMod, setLoadingMod] = useState(true);
  const [error, setError]         = useState(null);
  const [tab, setTab]             = useState('model');
  const [selectedSection, setSelectedSection] = useState(null);
  const [diagramUrl, setDiagramUrl] = useState(null);

  useEffect(() => {
    const stored = sessionStorage.getItem('um_user');
    const token  = sessionStorage.getItem('um_token');
    if (!stored || !token) { router.replace('/tg'); return; }
    setUser(JSON.parse(stored));
    loadModels();
  }, []);

  const loadModels = async () => {
    setLoadingMod(true);
    try {
      const res = await authFetch('/parts/bot/catalog-models');
      if (res.ok) setModels(await res.json());
    } finally {
      setLoadingMod(false);
    }
  };

  const searchByModel = async () => {
    if (!model || !desc.trim()) return;
    setLoading(true);
    setError(null);
    setResults([]);
    setSections([]);
    try {
      const res = await authFetch('/parts/search-by-model', {
        method: 'POST',
        body: JSON.stringify({ model_code: model, description: desc }),
      });
      if (!res.ok) { setError('Sin resultados para ese modelo'); return; }
      const data = await res.json();
      setResults(data);
    } catch (e) {
      setError(`Error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const loadSections = async (modelCode) => {
    setSections([]);
    setResults([]);
    setSelectedSection(null);
    setDiagramUrl(null);
    const res = await authFetch(`/parts/model/${modelCode}/all-sections`);
    if (res.ok) setSections(await res.json());
  };

  const openSection = (section) => {
    setSelectedSection(section);
    // diagram_url es una URL pública de MinIO — usarla directo
    setDiagramUrl(section.diagram_url || null);
  };

  return (
    <div style={{ minHeight: '100vh', background: '#0a0a0c', paddingBottom: '5.5rem' }}>
      {/* Header */}
      <div style={{ background: '#13131a', borderBottom: '1px solid rgba(255,255,255,0.06)', padding: '0.9rem 1.25rem' }}>
        <p style={{ margin: 0, fontWeight: 900, fontSize: '0.9rem', color: '#fff' }}>Catálogo de Repuestos</p>
        <p style={{ margin: 0, fontSize: '0.6rem', color: '#606075' }}>Buscar por modelo o descripción</p>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '0.4rem', padding: '0.75rem 1rem 0.5rem' }}>
        {[['model', 'Por Modelo'], ['desc', 'Por Descripción']].map(([v, l]) => (
          <button key={v} onClick={() => { setTab(v); setResults([]); setSections([]); setError(null); }}
            style={{ padding: '0.4rem 0.9rem', borderRadius: 20, border: 'none', background: tab === v ? '#ff5f33' : 'rgba(255,255,255,0.06)', color: tab === v ? '#fff' : '#606075', fontWeight: 700, fontSize: '0.68rem', cursor: 'pointer' }}>
            {l}
          </button>
        ))}
      </div>

      <div style={{ padding: '0 1rem' }}>
        {/* Selector de modelo */}
        <div style={{ marginBottom: '0.5rem' }}>
          <label style={{ fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, display: 'block', marginBottom: 6 }}>Modelo UM</label>
          {loadingMod ? (
            <p style={{ color: '#606075', fontSize: '0.7rem' }}>Cargando modelos...</p>
          ) : (
            <select
              value={model}
              onChange={e => { setModel(e.target.value); if (e.target.value && tab === 'model') loadSections(e.target.value); }}
              style={{ width: '100%', background: '#13131a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 10, padding: '0.7rem 0.9rem', color: model ? '#fff' : '#606075', fontSize: '0.82rem', outline: 'none' }}
            >
              <option value="">Seleccionar modelo...</option>
              {models.map(m => (
                <option key={m.catalog_model_code} value={m.catalog_model_code}>{m.vehicle_model}</option>
              ))}
            </select>
          )}
        </div>

        {/* Búsqueda por descripción */}
        {tab === 'desc' && (
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
            <input
              value={desc}
              onChange={e => setDesc(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && searchByModel()}
              placeholder="Ej: bujía, freno trasero..."
              style={{ flex: 1, background: '#13131a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 10, padding: '0.7rem 0.9rem', color: '#fff', fontSize: '0.82rem', outline: 'none' }}
            />
            <button
              onClick={searchByModel}
              disabled={loading || !model || !desc.trim()}
              style={{ padding: '0.7rem 1rem', background: '#ff5f33', border: 'none', borderRadius: 10, color: '#fff', fontWeight: 800, fontSize: '0.82rem', cursor: 'pointer', opacity: loading || !model || !desc.trim() ? 0.5 : 1 }}
            >
              {loading ? '...' : 'Buscar'}
            </button>
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{ padding: '0.7rem 1rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 10, marginBottom: '0.5rem' }}>
            <p style={{ margin: 0, fontSize: '0.72rem', color: '#ef4444', fontWeight: 700 }}>{error}</p>
          </div>
        )}

        {/* Secciones (tab modelo) */}
        {tab === 'model' && sections.length > 0 && (
          <>
            <p style={{ margin: '0.5rem 0 0.4rem', fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>Secciones del catálogo — toca para ver diagrama</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
              {sections.map(s => (
                <div
                  key={s.section_id}
                  onClick={() => openSection(s)}
                  style={{ background: '#13131a', borderRadius: 10, padding: '0.65rem 0.9rem', border: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: s.diagram_url ? 'pointer' : 'default' }}
                >
                  <div>
                    <span style={{ fontSize: '0.62rem', color: '#ff8c5a', fontWeight: 800, marginRight: '0.5rem' }}>{s.section_code}</span>
                    <span style={{ fontSize: '0.72rem', color: '#e2e2f0', fontWeight: 600 }}>{s.section_name}</span>
                  </div>
                  {s.diagram_url && <span style={{ fontSize: '0.6rem', color: '#606075' }}>→</span>}
                </div>
              ))}
            </div>
          </>
        )}

        {/* Resultados de búsqueda */}
        {results.length > 0 && (
          <>
            <p style={{ margin: '0.5rem 0 0.4rem', fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>Secciones encontradas</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
              {results.map(r => (
                <div key={r.section_id} style={{ background: '#13131a', borderRadius: 10, padding: '0.75rem 0.9rem', border: '1px solid rgba(255,95,51,0.15)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ fontSize: '0.62rem', color: '#ff8c5a', fontWeight: 800 }}>{r.section_code}</span>
                  </div>
                  <p style={{ margin: 0, fontSize: '0.74rem', color: '#e2e2f0', fontWeight: 600 }}>{r.section_name}</p>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Bottom sheet — diagrama */}
      {selectedSection && (
        <div
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(4px)', zIndex: 50, display: 'flex', alignItems: 'flex-end' }}
          onClick={() => { setSelectedSection(null); setDiagramUrl(null); }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{ width: '100%', background: '#13131a', borderRadius: '20px 20px 0 0', padding: '1.25rem 1.25rem 2rem', maxHeight: '90vh', overflowY: 'auto' }}
          >
            <div style={{ width: 36, height: 4, background: 'rgba(255,255,255,0.12)', borderRadius: 2, margin: '0 auto 1rem' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
              <div>
                <span style={{ fontSize: '0.6rem', color: '#ff8c5a', fontWeight: 800 }}>{selectedSection.section_code}</span>
                <p style={{ margin: '2px 0 0', fontWeight: 800, fontSize: '0.88rem', color: '#fff' }}>{selectedSection.section_name}</p>
              </div>
              <button onClick={() => { setSelectedSection(null); setDiagramUrl(null); }} style={{ background: 'none', border: 'none', color: '#606075', cursor: 'pointer', fontSize: '1.2rem' }}>✕</button>
            </div>

            {diagramUrl && (
              <img
                src={diagramUrl}
                alt={selectedSection.section_name}
                style={{ width: '100%', borderRadius: 10, border: '1px solid rgba(255,255,255,0.06)' }}
              />
            )}
            {!loadingDiagram && !diagramUrl && !selectedSection.diagram_url && (
              <div style={{ textAlign: 'center', padding: '2rem', color: '#606075', fontSize: '0.75rem' }}>Sin diagrama disponible para esta sección</div>
            )}
          </div>
        </div>
      )}

      <TgNav userRole={user?.role} />
    </div>
  );
}
