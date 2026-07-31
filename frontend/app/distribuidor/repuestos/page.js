'use client';

import { useState, useEffect } from 'react';
import AdminLayout from '../../admin-layout';
import { authFetch } from '../../../lib/authFetch';
import VoiceInput from '../../../components/tg/VoiceInput';
import CameraInput from '../../../components/tg/CameraInput';

// ---------------------------------------------------------------------------
// Style tokens copied BY VALUE from `entrega/page.js` (Design ADR 10) --
// deliberately NOT imported/shared, so the two Distribuidor screens can
// diverge independently later. Same literal shapes/values, this file's own
// copy.
// ---------------------------------------------------------------------------
const sectionStyle = { display: 'flex', flexDirection: 'column', gap: '1rem' };
const cardStyle = { maxWidth: '1200px', margin: '0 auto', width: '100%' };
const labelStyle = { display: 'flex', flexDirection: 'column', gap: '0.35rem', fontSize: '0.72rem', fontWeight: 700, color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase', letterSpacing: '0.05em' };
const inputStyle = { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '0.6rem 0.85rem', color: '#fff', fontSize: '0.85rem', outline: 'none', textTransform: 'none' };
const hintStyle = { margin: 0, fontSize: '0.68rem', color: 'rgba(255,255,255,0.45)', textTransform: 'none', fontWeight: 400, letterSpacing: 'normal' };
const emptyStateStyle = { ...hintStyle, fontSize: '0.85rem', textAlign: 'center', padding: '2rem 0' };
const thStyle = { textAlign: 'left', padding: '0.7rem 0.9rem', color: 'rgba(255,255,255,0.4)', fontWeight: 700, fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid rgba(255,255,255,0.1)' };
const tdStyle = { padding: '0.7rem 0.9rem', fontSize: '0.82rem', color: '#fff', borderBottom: '1px solid rgba(255,255,255,0.06)' };
// Explicit background/color on every <option> -- without it, the dropdown
// popup inherits light text on the browser's default light background and
// is invisible until hovered (matches historical-orders/page.js's fix for
// the same bug).
const optionStyle = { background: '#1a1a22', color: '#fff' };

// ---------------------------------------------------------------------------
// Data hooks
// ---------------------------------------------------------------------------
function useCatalogModels() {
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  useEffect(() => {
    authFetch('/parts/bot/catalog-models')
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error('request failed'))))
      .then((data) => setModels(Array.isArray(data) ? data : []))
      .catch(() => setError('No se pudieron cargar los modelos.'))
      .finally(() => setLoading(false));
  }, []);
  return { models, loading, error };
}

function useModelSections(modelCode) {
  const [sections, setSections] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!modelCode) { setSections([]); setError(null); return; }
    let cancelled = false;
    setLoading(true);
    setError(null);
    authFetch(`/parts/model/${modelCode}/all-sections`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error('request failed'))))
      .then((data) => { if (!cancelled) setSections(Array.isArray(data) ? data : []); })
      .catch(() => { if (!cancelled) setError('No se pudieron cargar las secciones.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [modelCode]);

  return { sections, loading, error };
}

function useDescriptionSearch(modelCode) {
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const search = async (description) => {
    if (!modelCode || !description?.trim()) return;
    setLoading(true); setError(null); setResults([]);
    try {
      const res = await authFetch('/parts/search-by-model', {
        method: 'POST',
        body: JSON.stringify({ model_code: modelCode, description }),
      });
      if (!res.ok) { setError('Sin resultados'); return; }
      setResults(await res.json());
    } catch (e) {
      setError(`Error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  return { results, loading, error, search };
}

function useSectionDetail() {
  const [section, setSection] = useState(null);
  const [diagramBlob, setDiagramBlob] = useState(null);
  const [diagramError, setDiagramError] = useState(null);
  const [loadingDiagram, setLoadingDiagram] = useState(false);
  const [items, setItems] = useState([]);
  const [itemsError, setItemsError] = useState(null);
  const [loadingItems, setLoadingItems] = useState(false);

  const open = async (s) => {
    setSection(s);
    setDiagramBlob(null);
    setDiagramError(null);
    setItems([]);
    setItemsError(null);

    if (s.diagram_url) {
      setLoadingDiagram(true);
      authFetch(`/parts/section/${s.section_id}/diagram-image`)
        .then((res) => (res.ok ? res.blob() : Promise.reject(new Error('request failed'))))
        .then((blob) => setDiagramBlob(URL.createObjectURL(blob)))
        .catch(() => setDiagramError('No se pudo cargar el diagrama.'))
        .finally(() => setLoadingDiagram(false));
    }

    setLoadingItems(true);
    try {
      const res = await authFetch(`/parts/section/${s.section_id}/items`);
      if (!res.ok) throw new Error('request failed');
      setItems(await res.json());
    } catch {
      setItemsError('No se pudieron cargar las piezas.');
    } finally {
      setLoadingItems(false);
    }
  };

  const close = () => {
    setSection(null);
    setDiagramBlob(null);
    setDiagramError(null);
    setItems([]);
    setItemsError(null);
  };

  return { section, diagramBlob, diagramError, loadingDiagram, items, itemsError, loadingItems, open, close };
}

// ---------------------------------------------------------------------------
// Presentational bits
// ---------------------------------------------------------------------------
function PageHeader() {
  return (
    <header className="page-header">
      <div>
        <h1 className="page-title">
          Consulta de <span style={{ fontStyle: 'italic', color: 'var(--accent-orange)', WebkitTextFillColor: 'var(--accent-orange)' }}>Repuestos</span>
        </h1>
        <p className="page-subtitle">Diagrama y lista de piezas por sección — solo consulta</p>
      </div>
    </header>
  );
}

const sectionRowStyle = (highlight) => ({
  background: '#13131a', borderRadius: 10, padding: '0.75rem 0.9rem',
  border: `1px solid ${highlight ? 'rgba(255,95,51,0.2)' : 'rgba(255,255,255,0.1)'}`,
  display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer',
});

function SectionRow({ s, highlight = false, onOpen }) {
  return (
    <div style={sectionRowStyle(highlight)} onClick={() => onOpen(s)}>
      <div style={{ minWidth: 0 }}>
        <span style={{ fontSize: '0.65rem', color: '#ff8c5a', fontWeight: 800, marginRight: '0.5rem' }}>{s.section_code}</span>
        <span style={{ fontSize: '0.8rem', color: '#e2e2f0', fontWeight: 600 }}>{s.section_name}</span>
      </div>
      <span style={{ fontSize: '0.68rem', color: '#606075', flexShrink: 0, marginLeft: '0.5rem' }}>
        {s.diagram_url ? 'Ver diagrama' : 'Ver lista'}
      </span>
    </div>
  );
}

function ModelSelect({ models, loading, value, onChange }) {
  return (
    <label style={labelStyle}>
      Modelo UM
      {loading ? (
        <p style={hintStyle}>Cargando modelos...</p>
      ) : (
        <select value={value} onChange={(e) => onChange(e.target.value)} style={inputStyle}>
          <option value="" style={optionStyle}>Seleccionar modelo...</option>
          {models.map((m) => (
            <option key={m.catalog_model_code} value={m.catalog_model_code} style={optionStyle}>{m.vehicle_model}</option>
          ))}
        </select>
      )}
    </label>
  );
}

function DescriptionSearchBar({ desc, setDesc, onSearch, loading, disabled }) {
  return (
    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginTop: '0.75rem' }}>
      <input
        value={desc}
        onChange={(e) => setDesc(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && onSearch(desc)}
        placeholder="Ej: bujía, freno trasero..."
        style={{ ...inputStyle, flex: 1 }}
      />
      <VoiceInput
        onTranscript={(text) => { setDesc(text); onSearch(text); }}
        disabled={loading}
        size={38}
      />
      <CameraInput
        mode="part"
        onResult={(data) => { if (data.description) { setDesc(data.description); onSearch(data.description); } }}
        disabled={loading}
        size={38}
      />
      <button
        type="button"
        onClick={() => onSearch(desc)}
        disabled={disabled || loading || !desc.trim()}
        className="btn-primary"
        style={{ opacity: disabled || loading || !desc.trim() ? 0.5 : 1 }}
      >
        {loading ? '...' : 'Buscar'}
      </button>
    </div>
  );
}

const priceCellStyle = { display: 'flex', alignItems: 'baseline', gap: '0.4rem', flexWrap: 'wrap' };
const preliminaryPillStyle = { fontSize: '0.6rem', fontWeight: 700, color: '#ffb020', background: 'rgba(255,176,32,0.12)', border: '1px solid rgba(255,176,32,0.3)', borderRadius: 6, padding: '0.15rem 0.4rem' };

function PriceCell({ item }) {
  return (
    <div style={priceCellStyle}>
      {item.precio_publico != null ? (
        <span style={{ fontWeight: 800, color: '#ff8c5a' }}>
          {new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(item.precio_publico)}
        </span>
      ) : (
        <span style={{ fontWeight: 700, color: '#606075' }}>Sin precio</span>
      )}
      {item.precio_publico != null && item.precio_es_preliminar && (
        <span style={preliminaryPillStyle}>Precio preliminar</span>
      )}
    </div>
  );
}

function ItemsTable({ items, loading, error }) {
  if (loading) return <p style={emptyStateStyle}>Cargando piezas...</p>;
  if (error) return <p style={{ ...emptyStateStyle, color: '#ef4444' }}>{error}</p>;
  if (items.length === 0) return <p style={emptyStateStyle}>Sin piezas para esta sección.</p>;
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th style={thStyle}>Pos.</th>
            <th style={thStyle}>Cód. Fábrica</th>
            <th style={thStyle}>Cód. UM</th>
            <th style={thStyle}>Descripción</th>
            <th style={thStyle}>Unidad</th>
            <th style={thStyle}>Precio Público</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => (
            <tr key={it.id}>
              <td style={tdStyle}>{it.order_num}</td>
              <td style={tdStyle}>{it.factory_part_number}</td>
              <td style={tdStyle}>{it.um_part_number || '—'}</td>
              <td style={tdStyle}>
                {it.description || 'N/D'}
                {it.description_es && (
                  <p style={{ ...hintStyle, marginTop: 2 }}>{it.description_es}</p>
                )}
              </td>
              <td style={tdStyle}>{it.unit || '—'}</td>
              <td style={tdStyle}><PriceCell item={it} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Pure CSS-grid breakpoint, no JS (Design ADR 12) -- 1024px matches
// `admin-layout.js`'s own sidebar-collapse breakpoint. Diagram panel is
// `position: sticky` only above that width.
function TwoPanelStyles() {
  return (
    <style>{`
      .repuestos-two-panel {
        display: flex;
        flex-direction: column;
        gap: 1.25rem;
      }
      @media (min-width: 1024px) {
        .repuestos-two-panel {
          display: grid;
          grid-template-columns: 1fr 1fr;
          align-items: start;
        }
        .repuestos-diagram-panel {
          position: sticky;
          top: 1rem;
        }
      }
    `}</style>
  );
}

function SectionDetail({ section, diagramBlob, diagramError, loadingDiagram, items, itemsError, loadingItems, onClose }) {
  return (
    <section className="glass p-6" style={{ ...sectionStyle, ...cardStyle, marginTop: '1.5rem' }}>
      <TwoPanelStyles />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <span style={{ fontSize: '0.65rem', color: '#ff8c5a', fontWeight: 800 }}>{section.section_code}</span>
          <h2 style={{ margin: '2px 0 0', fontWeight: 800, fontSize: '1rem', color: '#fff' }}>{section.section_name}</h2>
        </div>
        <button type="button" className="btn-secondary" onClick={onClose}>Cerrar</button>
      </div>

      <div className="repuestos-two-panel">
        <div className="repuestos-diagram-panel">
          {loadingDiagram && <p style={emptyStateStyle}>Cargando diagrama...</p>}
          {diagramBlob && (
            <img
              src={diagramBlob}
              alt={section.section_name}
              style={{ width: '100%', borderRadius: 10, border: '1px solid rgba(255,255,255,0.1)', display: 'block' }}
            />
          )}
          {!loadingDiagram && diagramError && (
            <p style={{ ...emptyStateStyle, color: '#ef4444' }}>{diagramError}</p>
          )}
          {!loadingDiagram && !diagramBlob && !diagramError && !section.diagram_url && (
            <p style={emptyStateStyle}>Sin diagrama disponible para esta sección.</p>
          )}
        </div>
        <div>
          <ItemsTable items={items} loading={loadingItems} error={itemsError} />
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Tab bodies
// ---------------------------------------------------------------------------
function ModelTabContent({ modelCode, sections, loading, error, onOpen }) {
  if (!modelCode) return <p style={hintStyle}>Seleccioná un modelo para ver sus secciones.</p>;
  if (loading) return <p style={hintStyle}>Cargando secciones...</p>;
  if (error) return <p style={{ color: '#ef4444', fontSize: '0.8rem' }}>{error}</p>;
  if (sections.length === 0) return <p style={emptyStateStyle}>Este modelo no tiene secciones cargadas.</p>;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
      {sections.map((s) => (
        <SectionRow key={s.section_id} s={s} onOpen={onOpen} />
      ))}
    </div>
  );
}

function DescriptionTabContent({ desc, setDesc, descApi, disabled, onOpen }) {
  return (
    <>
      <DescriptionSearchBar
        desc={desc}
        setDesc={setDesc}
        onSearch={descApi.search}
        loading={descApi.loading}
        disabled={disabled}
      />
      {descApi.error && (
        <p style={{ color: '#ef4444', fontSize: '0.8rem' }}>{descApi.error}</p>
      )}
      {descApi.results.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
          {descApi.results.map((s) => (
            <SectionRow key={s.section_id} s={s} highlight onOpen={onOpen} />
          ))}
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
const TAB_MODEL = 'model';
const TAB_DESC = 'desc';

function TabSwitcher({ tab, onChange }) {
  return (
    <div style={{ display: 'flex', gap: '0.5rem' }}>
      <button type="button" className={tab === TAB_MODEL ? 'btn-primary' : 'btn-secondary'} onClick={() => onChange(TAB_MODEL)}>
        Por Modelo
      </button>
      <button type="button" className={tab === TAB_DESC ? 'btn-primary' : 'btn-secondary'} onClick={() => onChange(TAB_DESC)}>
        Por Descripción
      </button>
    </div>
  );
}

export default function DistribuidorRepuestosPage() {
  const { models, loading: loadingModels, error: modelsError } = useCatalogModels();
  const [modelCode, setModelCode] = useState('');
  const [tab, setTab] = useState(TAB_MODEL);
  const [desc, setDesc] = useState('');

  const { sections, loading: loadingSections, error: sectionsError } = useModelSections(modelCode);
  const descApi = useDescriptionSearch(modelCode);
  const detail = useSectionDetail();

  const handleModelChange = (code) => {
    setModelCode(code);
    detail.close();
  };

  return (
    <AdminLayout fullWidth>
      <PageHeader />

      <section className="glass p-6" style={{ ...sectionStyle, ...cardStyle }}>
        <ModelSelect models={models} loading={loadingModels} value={modelCode} onChange={handleModelChange} />
        {modelsError && (
          <p style={{ color: '#ef4444', fontSize: '0.8rem' }}>{modelsError}</p>
        )}

        <TabSwitcher tab={tab} onChange={setTab} />

        {tab === TAB_MODEL && (
          <ModelTabContent
            modelCode={modelCode}
            sections={sections}
            loading={loadingSections}
            error={sectionsError}
            onOpen={detail.open}
          />
        )}

        {tab === TAB_DESC && (
          <DescriptionTabContent
            desc={desc}
            setDesc={setDesc}
            descApi={descApi}
            disabled={!modelCode}
            onOpen={detail.open}
          />
        )}
      </section>

      {detail.section && (
        <SectionDetail
          section={detail.section}
          diagramBlob={detail.diagramBlob}
          diagramError={detail.diagramError}
          loadingDiagram={detail.loadingDiagram}
          items={detail.items}
          itemsError={detail.itemsError}
          loadingItems={detail.loadingItems}
          onClose={detail.close}
        />
      )}
    </AdminLayout>
  );
}
