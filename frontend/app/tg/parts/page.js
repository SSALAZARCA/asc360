'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { authFetch } from '../../../lib/authFetch';
import TgNav from '../../../components/tg/TgNav';
import VoiceInput from '../../../components/tg/VoiceInput';
import CameraInput from '../../../components/tg/CameraInput';

// Explicit background/color on every <option> -- without it, the dropdown
// popup inherits light text on the browser's default light background and
// is invisible until hovered (matches historical-orders/page.js's fix for
// the same bug).
const optionStyle = { background: '#1a1a22', color: '#fff' };

export default function TgParts() {
  const router = useRouter();
  const [user, setUser]             = useState(null);
  const [models, setModels]         = useState([]);
  const [model, setModel]           = useState('');
  const [desc, setDesc]             = useState('');
  const [results, setResults]       = useState([]);
  const [sections, setSections]     = useState([]);
  const [loading, setLoading]       = useState(false);
  const [loadingMod, setLoadingMod] = useState(true);
  const [error, setError]           = useState(null);
  const [tab, setTab]               = useState('model');

  // Bottom sheet de sección
  const [sheet, setSheet]           = useState(null);  // { section_id, section_code, section_name, diagram_url, model_code }
  const [diagramBlob, setDiagramBlob] = useState(null);
  const [loadingDiagram, setLoadingDiagram] = useState(false);
  const [sectionItems, setSectionItems] = useState([]);
  const [loadingItems, setLoadingItems] = useState(false);
  const [itemsError, setItemsError]     = useState(null);
  const [posCode, setPosCode]       = useState('');
  const [partResult, setPartResult] = useState(null);
  const [partError, setPartError]   = useState(null);
  const [searchingPart, setSearchingPart] = useState(false);

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

  const loadSections = async (modelCode) => {
    setSections([]); setResults([]); closeSheet();
    const res = await authFetch(`/parts/model/${modelCode}/all-sections`);
    if (res.ok) setSections(await res.json());
  };

  const searchByDesc = async (descOverride) => {
    const d = descOverride ?? desc;
    if (!model || !d.trim()) return;
    setLoading(true); setError(null); setResults([]); setSections([]);
    try {
      const res = await authFetch('/parts/search-by-model', {
        method: 'POST',
        body: JSON.stringify({ model_code: model, description: d }),
      });
      if (!res.ok) { setError('Sin resultados'); return; }
      setResults(await res.json());
    } catch (e) { setError(`Error: ${e.message}`); }
    finally { setLoading(false); }
  };

  const openSheet = async (s) => {
    setSheet(s);
    setPosCode(''); setPartResult(null); setPartError(null);
    setDiagramBlob(null);
    setSectionItems([]); setItemsError(null);

    const loadItems = async () => {
      setLoadingItems(true);
      try {
        const res = await authFetch(`/parts/section/${s.section_id}/items`);
        if (!res.ok) { setItemsError('Error al cargar las piezas de la sección'); return; }
        setSectionItems(await res.json());
      } catch (e) { setItemsError(`Error: ${e.message}`); }
      finally { setLoadingItems(false); }
    };

    const loadDiagram = async () => {
      if (!s.diagram_url) return;
      setLoadingDiagram(true);
      try {
        const res = await authFetch(`/parts/section/${s.section_id}/diagram-image`);
        if (res.ok) {
          const blob = await res.blob();
          setDiagramBlob(URL.createObjectURL(blob));
        }
      } finally { setLoadingDiagram(false); }
    };

    await Promise.all([loadItems(), loadDiagram()]);
  };

  const closeSheet = () => {
    setSheet(null); setDiagramBlob(null);
    setSectionItems([]); setItemsError(null);
    setPosCode(''); setPartResult(null); setPartError(null);
  };

  const lookupPart = async () => {
    if (!posCode.trim() || !sheet) return;
    setSearchingPart(true); setPartResult(null); setPartError(null);
    try {
      const res = await authFetch(`/parts/section/${sheet.section_id}/item/${posCode.trim().toUpperCase()}`);
      if (res.status === 404) { setPartError('Código de posición no encontrado en esta sección'); return; }
      if (!res.ok) { setPartError('Error al buscar la pieza'); return; }
      setPartResult(await res.json());
    } catch (e) { setPartError(`Error: ${e.message}`); }
    finally { setSearchingPart(false); }
  };

  const sectionRow = (s, highlight = false) => (
    <div
      key={s.section_id}
      onClick={() => openSheet(s)}
      style={{
        background: '#13131a', borderRadius: 10, padding: '0.75rem 0.9rem',
        border: `1px solid ${highlight ? 'rgba(255,95,51,0.2)' : 'rgba(255,255,255,0.05)'}`,
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer',
        WebkitTapHighlightColor: 'transparent',
      }}
    >
      <div style={{ minWidth: 0 }}>
        <span style={{ fontSize: '0.62rem', color: '#ff8c5a', fontWeight: 800, marginRight: '0.5rem' }}>{s.section_code}</span>
        <span style={{ fontSize: '0.72rem', color: '#e2e2f0', fontWeight: 600 }}>{s.section_name}</span>
      </div>
      <span style={{ fontSize: '0.65rem', color: '#606075', flexShrink: 0, marginLeft: '0.5rem' }}>
        {s.diagram_url ? '🔍' : '→'}
      </span>
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100dvh', background: '#0a0a0c' }}>

      {/* Header */}
      <div style={{ background: '#13131a', borderBottom: '1px solid rgba(255,255,255,0.06)', padding: '0.9rem 1.25rem', display: 'flex', alignItems: 'center', gap: '0.75rem', flexShrink: 0 }}>
        <img src="/logo.png" alt="UM" style={{ height: 28, width: 'auto', objectFit: 'contain', flexShrink: 0, opacity: 0.9 }} />
        <div>
          <p style={{ margin: 0, fontWeight: 900, fontSize: '0.9rem', color: '#fff' }}>Catálogo de Repuestos</p>
          <p style={{ margin: 0, fontSize: '0.6rem', color: '#606075' }}>Seleccioná un modelo para explorar secciones</p>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '0.4rem', padding: '0.75rem 1rem 0.5rem', flexShrink: 0 }}>
        {[['model', 'Por Modelo'], ['desc', 'Por Descripción']].map(([v, l]) => (
          <button key={v}
            onClick={() => { setTab(v); setResults([]); setSections([]); setError(null); closeSheet(); }}
            style={{ padding: '0.4rem 0.9rem', borderRadius: 20, border: 'none', background: tab === v ? '#ff5f33' : 'rgba(255,255,255,0.06)', color: tab === v ? '#fff' : '#606075', fontWeight: 700, fontSize: '0.68rem', cursor: 'pointer' }}>
            {l}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '0 1rem', paddingBottom: '5.5rem' }}>

        {/* Selector de modelo */}
        <div style={{ marginBottom: '0.65rem' }}>
          <label style={{ fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, display: 'block', marginBottom: 6 }}>Modelo UM</label>
          {loadingMod ? (
            <p style={{ color: '#606075', fontSize: '0.7rem' }}>Cargando modelos...</p>
          ) : (
            <select value={model}
              onChange={e => { setModel(e.target.value); if (e.target.value && tab === 'model') loadSections(e.target.value); }}
              style={{ width: '100%', background: '#13131a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 10, padding: '0.7rem 0.9rem', color: model ? '#fff' : '#606075', fontSize: '0.82rem', outline: 'none' }}>
              <option value="" style={optionStyle}>Seleccionar modelo...</option>
              {models.map(m => (
                <option key={m.catalog_model_code} value={m.catalog_model_code} style={optionStyle}>{m.vehicle_model}</option>
              ))}
            </select>
          )}
        </div>

        {/* Búsqueda por descripción */}
        {tab === 'desc' && (
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.65rem', alignItems: 'center' }}>
            <input value={desc} onChange={e => setDesc(e.target.value)} onKeyDown={e => e.key === 'Enter' && searchByDesc()}
              placeholder="Ej: bujía, freno trasero..."
              style={{ flex: 1, background: '#13131a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 10, padding: '0.7rem 0.9rem', color: '#fff', fontSize: '1rem', outline: 'none' }} />
            <VoiceInput
              onTranscript={text => { setDesc(text); searchByDesc(text); }}
              onError={msg => setError(msg)}
              disabled={loading}
              size={38}
            />
            <CameraInput
              mode="part"
              onResult={data => {
                if (data.description) { setDesc(data.description); searchByDesc(data.description); }
              }}
              onError={msg => setError(msg)}
              disabled={loading}
              size={38}
            />
            <button onClick={searchByDesc} disabled={loading || !model || !desc.trim()}
              style={{ padding: '0.7rem 1rem', background: '#ff5f33', border: 'none', borderRadius: 10, color: '#fff', fontWeight: 800, fontSize: '0.82rem', cursor: 'pointer', opacity: loading || !model || !desc.trim() ? 0.5 : 1 }}>
              {loading ? '...' : 'Buscar'}
            </button>
          </div>
        )}

        {error && (
          <div style={{ padding: '0.65rem 0.9rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 10, marginBottom: '0.5rem' }}>
            <p style={{ margin: 0, fontSize: '0.72rem', color: '#ef4444', fontWeight: 700 }}>{error}</p>
          </div>
        )}

        {/* Lista de secciones */}
        {tab === 'model' && sections.length > 0 && (
          <>
            <p style={{ margin: '0.25rem 0 0.4rem', fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>
              Secciones — tocá para ver diagrama y buscar pieza
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
              {sections.map(s => sectionRow(s))}
            </div>
          </>
        )}

        {/* Resultados de búsqueda por descripción */}
        {results.length > 0 && (
          <>
            <p style={{ margin: '0.25rem 0 0.4rem', fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>
              Secciones encontradas — tocá para ver diagrama
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
              {results.map(s => sectionRow(s, true))}
            </div>
          </>
        )}
      </div>

      {/* ── Bottom sheet: diagrama + buscador de pieza ── */}
      {sheet && (
        <div
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.82)', backdropFilter: 'blur(4px)', zIndex: 50, display: 'flex', alignItems: 'flex-end' }}
          onClick={closeSheet}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{ width: '100%', background: '#13131a', borderRadius: '20px 20px 0 0', padding: '1rem 1.1rem 2.5rem', maxHeight: '92vh', overflowY: 'auto' }}
          >
            {/* Handle */}
            <div style={{ width: 36, height: 4, background: 'rgba(255,255,255,0.12)', borderRadius: 2, margin: '0 auto 1rem' }} />

            {/* Título */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.9rem' }}>
              <div>
                <span style={{ fontSize: '0.58rem', color: '#ff8c5a', fontWeight: 800 }}>{sheet.section_code}</span>
                <p style={{ margin: '2px 0 0', fontWeight: 800, fontSize: '0.9rem', color: '#fff' }}>{sheet.section_name}</p>
              </div>
              <button onClick={closeSheet} style={{ background: 'none', border: 'none', color: '#606075', cursor: 'pointer', fontSize: '1.1rem', padding: '0.2rem' }}>✕</button>
            </div>

            {/* Diagrama */}
            {loadingDiagram && (
              <div style={{ textAlign: 'center', padding: '2rem 0', color: '#606075', fontSize: '0.72rem' }}>Cargando diagrama...</div>
            )}
            {diagramBlob && (
              <div style={{ background: '#fff', borderRadius: 10, border: '1px solid rgba(255,255,255,0.06)', padding: '0.6rem', marginBottom: '1rem' }}>
                <img
                  src={diagramBlob}
                  alt={sheet.section_name}
                  style={{ width: '100%', borderRadius: 6, display: 'block' }}
                />
              </div>
            )}
            {!loadingDiagram && !diagramBlob && !sheet.diagram_url && (
              <div style={{ textAlign: 'center', padding: '1.5rem 0', color: '#606075', fontSize: '0.72rem', marginBottom: '1rem' }}>
                Sin diagrama disponible para esta sección
              </div>
            )}

            {/* Lista de piezas de la sección */}
            <div style={{ marginBottom: '1rem' }}>
              <p style={{ margin: '0 0 0.5rem', fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700 }}>
                Piezas de esta sección
              </p>
              {loadingItems && (
                <div style={{ textAlign: 'center', padding: '1rem 0', color: '#606075', fontSize: '0.72rem' }}>Cargando piezas...</div>
              )}
              {itemsError && (
                <div style={{ padding: '0.6rem 0.8rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 10, marginBottom: '0.5rem' }}>
                  <p style={{ margin: 0, fontSize: '0.7rem', color: '#ef4444', fontWeight: 700 }}>{itemsError}</p>
                </div>
              )}
              {!loadingItems && !itemsError && sectionItems.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', maxHeight: '14rem', overflowY: 'auto' }}>
                  {sectionItems.map(item => (
                    <div key={item.id} style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: '0.55rem 0.7rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.5rem' }}>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.4rem', marginBottom: 2 }}>
                          <span style={{ fontSize: '0.6rem', fontWeight: 800, color: '#ff8c5a' }}>{item.order_num}</span>
                          <span style={{ fontSize: '0.65rem', fontWeight: 700, color: '#e2e2f0' }}>{item.factory_part_number}</span>
                        </div>
                        <p style={{ margin: 0, fontSize: '0.68rem', color: '#a0a0b5', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {item.description_es || item.description || '—'}
                        </p>
                      </div>
                      <div style={{ flexShrink: 0, textAlign: 'right' }}>
                        {item.precio_publico != null ? (
                          <p style={{ margin: 0, fontSize: '0.72rem', fontWeight: 800, color: '#ff8c5a' }}>
                            {new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(item.precio_publico)}
                          </p>
                        ) : (
                          <p style={{ margin: 0, fontSize: '0.65rem', fontWeight: 700, color: '#606075' }}>Sin precio</p>
                        )}
                        {item.precio_publico != null && item.precio_es_preliminar && (
                          <span style={{ fontSize: '0.5rem', fontWeight: 700, color: '#ffb020', background: 'rgba(255,176,32,0.12)', border: '1px solid rgba(255,176,32,0.3)', borderRadius: 6, padding: '0.1rem 0.3rem', display: 'inline-block', marginTop: 2 }}>
                            Precio preliminar
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {!loadingItems && !itemsError && sectionItems.length === 0 && (
                <div style={{ textAlign: 'center', padding: '0.75rem 0', color: '#606075', fontSize: '0.68rem' }}>Sin piezas registradas</div>
              )}
            </div>

            {/* Buscador de pieza por código de posición */}
            <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '1rem' }}>
              <p style={{ margin: '0 0 0.5rem', fontSize: '0.55rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700 }}>
                Buscar pieza por código de posición
              </p>
              <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.6rem' }}>
                <input
                  value={posCode}
                  onChange={e => setPosCode(e.target.value.toUpperCase())}
                  onKeyDown={e => e.key === 'Enter' && lookupPart()}
                  placeholder="Ej: A1, B3, C12..."
                  style={{ flex: 1, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 10, padding: '0.65rem 0.9rem', color: '#fff', fontSize: '0.85rem', fontWeight: 700, letterSpacing: '0.05em', outline: 'none' }}
                />
                <button onClick={lookupPart} disabled={searchingPart || !posCode.trim()}
                  style={{ padding: '0.65rem 1rem', background: '#ff5f33', border: 'none', borderRadius: 10, color: '#fff', fontWeight: 800, fontSize: '0.82rem', cursor: 'pointer', opacity: searchingPart || !posCode.trim() ? 0.5 : 1 }}>
                  {searchingPart ? '...' : 'Buscar'}
                </button>
              </div>

              {partError && (
                <div style={{ padding: '0.6rem 0.8rem', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 10, marginBottom: '0.5rem' }}>
                  <p style={{ margin: 0, fontSize: '0.7rem', color: '#ef4444', fontWeight: 700 }}>{partError}</p>
                </div>
              )}

              {partResult && (
                <div style={{ background: 'rgba(255,95,51,0.06)', border: '1px solid rgba(255,95,51,0.2)', borderRadius: 12, padding: '0.9rem 1rem' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.4rem' }}>
                    {[
                      ['Posición',     partResult.order_num],
                      ['Cód. Fábrica', partResult.factory_part_number],
                      ['Cód. UM',      partResult.um_part_number || '—'],
                      ['Unidad',       partResult.unit || '—'],
                    ].map(([l, v]) => (
                      <div key={l} style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: '0.5rem 0.65rem' }}>
                        <p style={{ margin: 0, fontSize: '0.48rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2 }}>{l}</p>
                        <p style={{ margin: 0, fontSize: '0.72rem', fontWeight: 800, color: '#ff8c5a', wordBreak: 'break-all' }}>{v}</p>
                      </div>
                    ))}
                  </div>
                  <div style={{ marginTop: '0.4rem', background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: '0.5rem 0.65rem' }}>
                    <p style={{ margin: '0 0 2px', fontSize: '0.48rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Precio Público</p>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.4rem', flexWrap: 'wrap' }}>
                      {partResult.precio_publico != null ? (
                        <p style={{ margin: 0, fontSize: '0.85rem', fontWeight: 800, color: '#ff8c5a' }}>
                          {new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(partResult.precio_publico)}
                        </p>
                      ) : (
                        <p style={{ margin: 0, fontSize: '0.75rem', fontWeight: 700, color: '#606075' }}>Sin precio</p>
                      )}
                      {partResult.precio_publico != null && partResult.precio_es_preliminar && (
                        <span style={{ fontSize: '0.55rem', fontWeight: 700, color: '#ffb020', background: 'rgba(255,176,32,0.12)', border: '1px solid rgba(255,176,32,0.3)', borderRadius: 6, padding: '0.15rem 0.4rem' }}>
                          Precio preliminar
                        </span>
                      )}
                    </div>
                  </div>
                  <div style={{ marginTop: '0.5rem', background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: '0.5rem 0.65rem' }}>
                    <p style={{ margin: '0 0 2px', fontSize: '0.48rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Descripción</p>
                    <p style={{ margin: 0, fontSize: '0.75rem', fontWeight: 700, color: '#e2e2f0' }}>{partResult.description}</p>
                    {partResult.description_es && (
                      <p style={{ margin: '2px 0 0', fontSize: '0.68rem', color: '#606075' }}>{partResult.description_es}</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <TgNav userRole={user?.role} />
    </div>
  );
}
