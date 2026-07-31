'use client';

import { useState, useEffect, useRef } from 'react';
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
const cardStyle = { maxWidth: '1600px', margin: '0 auto', width: '100%' };
const labelStyle = { display: 'flex', flexDirection: 'column', gap: '0.35rem', fontSize: '0.72rem', fontWeight: 700, color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase', letterSpacing: '0.05em' };
const inputStyle = { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '0.6rem 0.85rem', color: '#fff', fontSize: '0.85rem', outline: 'none', textTransform: 'none' };
const hintStyle = { margin: 0, fontSize: '0.68rem', color: 'rgba(255,255,255,0.45)', textTransform: 'none', fontWeight: 400, letterSpacing: 'normal' };
const emptyStateStyle = { ...hintStyle, fontSize: '0.85rem', textAlign: 'center', padding: '2rem 0' };
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

// Copied by value from `entrega/page.js` / `settings/page.js`'s house
// convention for reading the logged-in user -- same shape, this file's own
// copy (see the style-token note at the top of this file for why).
function useCurrentUser() {
  const [user, setUser] = useState(null);
  useEffect(() => {
    const stored = sessionStorage.getItem('um_user');
    if (stored) {
      try { setUser(JSON.parse(stored)); } catch { setUser(null); }
    }
  }, []);
  return user;
}

// Superadmin-only diagram-image replacement. `upload` takes an `onSuccess`
// callback instead of owning the re-fetch itself, so it stays decoupled
// from `useSectionDetail`'s internals -- the caller decides how to refresh.
function useDiagramUpload() {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);

  const upload = async (sectionId, file, onSuccess) => {
    setUploading(true);
    setUploadError(null);
    try {
      const fd = new FormData();
      fd.append('image_file', file);
      const res = await authFetch(`/parts/admin/sections/${sectionId}/diagram`, { method: 'POST', body: fd });
      if (!res.ok) throw new Error('upload failed');
      await onSuccess();
    } catch {
      setUploadError('No se pudo reemplazar la imagen.');
    } finally {
      setUploading(false);
    }
  };

  return { uploading, uploadError, upload };
}

// Bundles the superadmin-only image-replace affordance (role check, upload
// state, hidden file input, click/change handlers) so the page component
// only wires one hook instead of four separate pieces of state.
function useDiagramReplace(section, onReplaced) {
  const user = useCurrentUser();
  const isSuperadmin = user?.role === 'superadmin';
  const { uploading, uploadError, upload } = useDiagramUpload();
  const fileInputRef = useRef();

  const onUploadClick = () => fileInputRef.current?.click();
  const onFileChange = (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || !section) return;
    upload(section.section_id, file, onReplaced);
  };

  return { isSuperadmin, uploading, uploadError, fileInputRef, onUploadClick, onFileChange };
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

function ModelSelect({ models, loading, value, onChange }) {
  return (
    <label style={labelStyle}>
      1. Motocicleta
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

// Mirrors the reference prototype's second dropdown (Sistema/Sección):
// always present, disabled until a model is chosen, one option per section.
function SectionSelect({ sections, loading, modelCode, value, onChange }) {
  return (
    <label style={labelStyle}>
      2. Sistema / Sección
      {loading ? (
        <p style={hintStyle}>Cargando secciones...</p>
      ) : (
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={!modelCode}
          style={{ ...inputStyle, opacity: modelCode ? 1 : 0.5, cursor: modelCode ? 'pointer' : 'not-allowed' }}
        >
          <option value="" style={optionStyle}>{modelCode ? 'Seleccionar sección...' : 'Elige moto primero...'}</option>
          {sections.map((s) => (
            <option key={s.section_id} value={s.section_id} style={optionStyle}>{s.section_code} · {s.section_name}</option>
          ))}
        </select>
      )}
    </label>
  );
}

function PieceCounter({ count }) {
  return (
    <div style={{ textAlign: 'right', minWidth: '160px' }}>
      <p style={hintStyle}>Total de Piezas Encontradas</p>
      <p style={{ margin: '2px 0 0', fontSize: '1.6rem', fontWeight: 800, color: '#ff8c5a' }}>{count}</p>
    </div>
  );
}

function DescriptionSearchBar({ desc, setDesc, onSearch, loading, disabled }) {
  return (
    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
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

const searchResultRowStyle = {
  background: '#13131a', borderRadius: 10, padding: '0.6rem 0.85rem',
  border: '1px solid rgba(255,95,51,0.2)',
  display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer',
};

function DescriptionSearchResults({ results, onOpen }) {
  if (results.length === 0) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
      {results.map((s) => (
        <div key={s.section_id} style={searchResultRowStyle} onClick={() => onOpen(s)}>
          <div style={{ minWidth: 0 }}>
            <span style={{ fontSize: '0.65rem', color: '#ff8c5a', fontWeight: 800, marginRight: '0.5rem' }}>{s.section_code}</span>
            <span style={{ fontSize: '0.8rem', color: '#e2e2f0', fontWeight: 600 }}>{s.section_name}</span>
          </div>
          <span style={{ fontSize: '0.68rem', color: '#606075', flexShrink: 0, marginLeft: '0.5rem' }}>Ver sección</span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Numbered-badge part cards -- mirrors the reference prototype's "circular
// numbered badge + details" list item, instead of a table row.
// ---------------------------------------------------------------------------
const partCardStyle = {
  background: '#111116', borderRadius: '1rem', padding: '1rem',
  border: '1px solid rgba(255,255,255,0.1)',
  display: 'flex', alignItems: 'center', gap: '1rem',
};
const partBadgeStyle = {
  flexShrink: 0, width: '2.5rem', height: '2.5rem', borderRadius: '50%',
  background: '#1a1a1a', border: '1px solid rgba(255,255,255,0.1)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  fontWeight: 800, fontSize: '0.8rem', color: '#fff',
};
const priceCellStyle = { display: 'flex', alignItems: 'baseline', gap: '0.4rem', flexWrap: 'wrap', flexShrink: 0 };
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

function PartCard({ item }) {
  return (
    <div style={partCardStyle} data-testid={`part-card-${item.id}`}>
      <div style={partBadgeStyle}>{item.order_num}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <h4 style={{ margin: 0, fontWeight: 700, fontSize: '0.85rem', color: '#fff' }}>
          {item.description || 'N/D'}
        </h4>
        {item.description_es && (
          <p style={{ ...hintStyle, marginTop: 2 }}>{item.description_es}</p>
        )}
        <p style={{ ...hintStyle, marginTop: 4 }}>
          Cód. Fábrica: <strong style={{ color: '#e2e2f0' }}>{item.factory_part_number}</strong>
          {' · '}Cód. UM: <strong style={{ color: '#e2e2f0' }}>{item.um_part_number || '—'}</strong>
          {' · '}Unidad: <strong style={{ color: '#e2e2f0' }}>{item.unit || '—'}</strong>
        </p>
      </div>
      <PriceCell item={item} />
    </div>
  );
}

function PartsList({ items, loading, error }) {
  if (loading) return <p style={emptyStateStyle}>Cargando piezas...</p>;
  if (error) return <p style={{ ...emptyStateStyle, color: '#ef4444' }}>{error}</p>;
  if (items.length === 0) {
    return (
      <div style={emptyStateStyle}>
        <p>Esperando modelo.</p>
        <p>Aquí aparecerán las piezas numeradas relacionadas al plano.</p>
      </div>
    );
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
      {items.map((it) => <PartCard key={it.id} item={it} />)}
    </div>
  );
}

// Fixed-height, independently-scrolling two-panel workspace -- mirrors the
// reference prototype's `h-auto lg:h-[750px]` grid (stacked, natural height,
// below 1024px; both panels locked to one shared height, each scrolling on
// its own, at 1024px+). No JS, pure CSS-grid breakpoint (Design ADR 12);
// 1024px matches `admin-layout.js`'s own sidebar-collapse breakpoint.
function TwoPanelStyles() {
  return (
    <style>{`
      .repuestos-two-panel {
        display: flex;
        flex-direction: column;
        gap: 1.25rem;
      }
      .repuestos-panel {
        display: flex;
        flex-direction: column;
        min-height: 420px;
      }
      .repuestos-panel-body {
        flex: 1;
        min-height: 0;
        overflow-y: auto;
      }
      @media (min-width: 1024px) {
        .repuestos-two-panel {
          display: grid;
          grid-template-columns: 1fr 1fr;
          height: 950px;
        }
        .repuestos-panel {
          height: 100%;
        }
      }
    `}</style>
  );
}

const panelOuterStyle = {
  background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: '1.25rem', overflow: 'hidden',
};
const panelHeaderStyle = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  padding: '1rem 1.25rem', borderBottom: '1px solid rgba(255,255,255,0.08)', flexShrink: 0,
};
const diagramViewportStyle = {
  flex: 1, minHeight: 0, background: '#fff', position: 'relative',
  display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem',
};
// `emptyStateStyle`'s light-gray-on-dark text becomes illegible once the
// viewport background is white -- a diagram-panel-only dark variant, used
// nowhere else, so `emptyStateStyle` itself stays unchanged for its other
// (still dark-background) callers.
const diagramEmptyStateStyle = { ...emptyStateStyle, color: 'rgba(20,20,26,0.65)' };
const panelFooterStyle = {
  padding: '0.75rem 1.25rem', borderTop: '1px solid rgba(255,255,255,0.08)',
  textAlign: 'center', flexShrink: 0,
};
const LENS_SIZE = 170;
const LENS_ZOOM = 2.5;

// Magnifying-glass zoom: a small circular lens follows the cursor and shows
// a magnified crop of the image at that exact position -- lets a técnico
// inspect one numbered callout without scaling (and losing context of) the
// whole diagram.
function ZoomableDiagram({ src, alt }) {
  const imgRef = useRef(null);
  const [hovering, setHovering] = useState(false);
  const [lens, setLens] = useState({ x: 0, y: 0, w: 0, h: 0 });

  const handleMouseMove = (e) => {
    const rect = imgRef.current.getBoundingClientRect();
    setLens({ x: e.clientX - rect.left, y: e.clientY - rect.top, w: rect.width, h: rect.height });
  };

  const lensLeft = lens.w > 0 ? Math.max(0, Math.min(lens.x - LENS_SIZE / 2, lens.w - LENS_SIZE)) : 0;
  const lensTop = lens.h > 0 ? Math.max(0, Math.min(lens.y - LENS_SIZE / 2, lens.h - LENS_SIZE)) : 0;

  return (
    <div style={{ position: 'relative', maxWidth: '100%', maxHeight: '100%', lineHeight: 0 }}>
      <img
        ref={imgRef}
        src={src}
        alt={alt}
        onMouseEnter={() => setHovering(true)}
        onMouseLeave={() => setHovering(false)}
        onMouseMove={handleMouseMove}
        style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', display: 'block', cursor: 'zoom-in' }}
      />
      {hovering && lens.w > 0 && (
        <div
          style={{
            position: 'absolute', left: lensLeft, top: lensTop,
            width: LENS_SIZE, height: LENS_SIZE, borderRadius: '50%',
            border: '2px solid rgba(255,140,90,0.9)', boxShadow: '0 4px 24px rgba(0,0,0,0.6)',
            pointerEvents: 'none', backgroundColor: '#fff',
            backgroundImage: `url(${src})`, backgroundRepeat: 'no-repeat',
            backgroundSize: `${lens.w * LENS_ZOOM}px ${lens.h * LENS_ZOOM}px`,
            backgroundPosition: `${-(lens.x * LENS_ZOOM - LENS_SIZE / 2)}px ${-(lens.y * LENS_ZOOM - LENS_SIZE / 2)}px`,
          }}
        />
      )}
    </div>
  );
}

const uploadBtnStyle = { fontSize: '0.68rem', padding: '0.3rem 0.6rem' };

function DiagramViewportContent({ section, diagramBlob, diagramError, loadingDiagram }) {
  if (!section) {
    return <p style={diagramEmptyStateStyle}>Seleccioná una motocicleta y una sección para cargar el esquema técnico en explosión.</p>;
  }
  if (loadingDiagram) {
    return <p style={diagramEmptyStateStyle}>Cargando diagrama...</p>;
  }
  if (diagramBlob) {
    return <ZoomableDiagram src={diagramBlob} alt={section.section_name} />;
  }
  if (diagramError) {
    return <p style={{ ...diagramEmptyStateStyle, color: '#ef4444' }}>{diagramError}</p>;
  }
  if (!section.diagram_url) {
    return <p style={diagramEmptyStateStyle}>Sin diagrama disponible para esta sección.</p>;
  }
  return null;
}

function DiagramPanel({
  section, diagramBlob, diagramError, loadingDiagram,
  isSuperadmin, uploading, uploadError, fileInputRef, onUploadClick, onFileChange,
}) {
  return (
    <div className="repuestos-panel" style={panelOuterStyle}>
      <div style={panelHeaderStyle}>
        <h3 style={{ margin: 0, fontWeight: 800, fontSize: '0.95rem', color: '#fff' }}>
          {section ? section.section_name : 'Plano de Ensamblaje'}
        </h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexShrink: 0 }}>
          {section && isSuperadmin && (
            <button
              type="button"
              className="btn-secondary"
              style={uploadBtnStyle}
              onClick={onUploadClick}
              disabled={uploading}
            >
              {uploading ? 'Subiendo...' : 'Reemplazar imagen'}
            </button>
          )}
          <span style={{ fontSize: '0.62rem', color: '#606075', textTransform: 'uppercase', letterSpacing: '0.05em', background: 'rgba(255,255,255,0.05)', padding: '0.2rem 0.5rem', borderRadius: 6, flexShrink: 0 }}>
            Despiece Técnico
          </span>
        </div>
      </div>
      {isSuperadmin && (
        <input
          ref={fileInputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={onFileChange}
          data-testid="diagram-file-input"
          style={{ display: 'none' }}
        />
      )}
      <div style={diagramViewportStyle}>
        <DiagramViewportContent section={section} diagramBlob={diagramBlob} diagramError={diagramError} loadingDiagram={loadingDiagram} />
      </div>
      {uploadError && (
        <p style={{ ...diagramEmptyStateStyle, color: '#ef4444', textAlign: 'left', padding: '0 1.25rem 0.75rem' }}>{uploadError}</p>
      )}
    </div>
  );
}

function ComponentsPanel({ items, loading, error }) {
  return (
    <div className="repuestos-panel" style={panelOuterStyle}>
      <div style={panelHeaderStyle}>
        <h3 style={{ margin: 0, fontWeight: 800, fontSize: '0.95rem', color: '#fff' }}>Listado de Componentes</h3>
      </div>
      <div className="repuestos-panel-body" style={{ padding: '1rem' }}>
        <PartsList items={items} loading={loading} error={error} />
      </div>
      <div style={panelFooterStyle}>
        <p style={hintStyle}>Todos los componentes listados garantizan piezas 100% de fábrica</p>
      </div>
    </div>
  );
}

// The two-panel workspace (diagram + parts list) mirrors the reference
// prototype's persistent layout: ALWAYS visible, each panel showing its own
// empty/loading/error/loaded state independently -- never a block that only
// appears after a section is picked.
function TwoPanelWorkspace({
  section, diagramBlob, diagramError, loadingDiagram, items, itemsError, loadingItems,
  isSuperadmin, uploading, uploadError, fileInputRef, onUploadClick, onFileChange,
}) {
  return (
    <section style={{ ...cardStyle, marginTop: '1.5rem' }}>
      <TwoPanelStyles />
      <div className="repuestos-two-panel">
        <DiagramPanel
          section={section}
          diagramBlob={diagramBlob}
          diagramError={diagramError}
          loadingDiagram={loadingDiagram}
          isSuperadmin={isSuperadmin}
          uploading={uploading}
          uploadError={uploadError}
          fileInputRef={fileInputRef}
          onUploadClick={onUploadClick}
          onFileChange={onFileChange}
        />
        <ComponentsPanel items={items} loading={loadingItems} error={itemsError} />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Description search -- an AI search entry point (text/voice/photo, already
// used by /tg/parts) that the reference prototype does not have at all. Kept
// as a separate, collapsible block BELOW the Motocicleta/Sistema/Contador
// row (never inside it, never replacing it), so it can never disturb that
// row's structure -- the prototype's own 3-column bar (ADR: Motocicleta,
// Sistema/Sección, Total de Piezas Encontradas, all in ONE row) stays intact
// regardless of whether this block is open.
function DescriptionSearchToggle({ open, onToggle, desc, setDesc, descApi, disabled, onOpen }) {
  return (
    <div style={{ marginTop: '1rem' }}>
      <button type="button" className="btn-secondary" onClick={onToggle}>
        {open ? 'Ocultar búsqueda por descripción' : 'Buscar por descripción'}
      </button>
      {open && (
        <div style={{ ...sectionStyle, marginTop: '0.75rem' }}>
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
          <DescriptionSearchResults results={descApi.results} onOpen={onOpen} />
        </div>
      )}
    </div>
  );
}

// Matches the reference prototype's single filter row: Motocicleta,
// Sistema/Sección, and the piece counter all together, always visible --
// never split across tabs or separate rows.
function FilterRow({ models, loadingModels, modelsError, modelCode, onModelChange, sections, loadingSections, sectionsError, sectionId, onSectionChange, pieceCount }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1.5rem', alignItems: 'flex-end' }}>
      <div style={{ flex: '1 1 220px' }}>
        <ModelSelect models={models} loading={loadingModels} value={modelCode} onChange={onModelChange} />
        {modelsError && (
          <p style={{ color: '#ef4444', fontSize: '0.8rem', marginTop: '0.4rem' }}>{modelsError}</p>
        )}
      </div>
      <div style={{ flex: '1 1 220px' }}>
        <SectionSelect
          sections={sections}
          loading={loadingSections}
          modelCode={modelCode}
          value={sectionId}
          onChange={onSectionChange}
        />
        {sectionsError && (
          <p style={{ color: '#ef4444', fontSize: '0.8rem', marginTop: '0.4rem' }}>{sectionsError}</p>
        )}
      </div>
      <PieceCounter count={pieceCount} />
    </div>
  );
}

// Bundles everything about "which model/section is currently selected and
// how the user got there" -- keeps the page component itself down to just
// the JSX composition.
function useRepuestosSelection() {
  const [modelCode, setModelCode] = useState('');
  const [sectionId, setSectionId] = useState('');
  const { sections, loading: loadingSections, error: sectionsError } = useModelSections(modelCode);
  const detail = useSectionDetail();

  const selectModel = (code) => {
    setModelCode(code);
    setSectionId('');
    detail.close();
  };

  const selectSection = (id) => {
    setSectionId(id);
    const section = sections.find((s) => s.section_id === id);
    if (section) detail.open(section);
    else detail.close();
  };

  const openSection = (section) => {
    setSectionId(section.section_id);
    detail.open(section);
  };

  return { modelCode, sectionId, sections, loadingSections, sectionsError, detail, selectModel, selectSection, openSection };
}

export default function DistribuidorRepuestosPage() {
  const { models, loading: loadingModels, error: modelsError } = useCatalogModels();
  const [descSearchOpen, setDescSearchOpen] = useState(false);
  const [desc, setDesc] = useState('');
  const {
    modelCode, sectionId, sections, loadingSections, sectionsError,
    detail, selectModel, selectSection, openSection,
  } = useRepuestosSelection();
  const descApi = useDescriptionSearch(modelCode);
  const diagramReplace = useDiagramReplace(detail.section, () => detail.open(detail.section));

  return (
    <AdminLayout fullWidth>
      <PageHeader />

      <section className="glass p-6" style={{ ...sectionStyle, ...cardStyle }}>
        <FilterRow
          models={models}
          loadingModels={loadingModels}
          modelsError={modelsError}
          modelCode={modelCode}
          onModelChange={selectModel}
          sections={sections}
          loadingSections={loadingSections}
          sectionsError={sectionsError}
          sectionId={sectionId}
          onSectionChange={selectSection}
          pieceCount={detail.items.length}
        />

        <DescriptionSearchToggle
          open={descSearchOpen}
          onToggle={() => setDescSearchOpen((v) => !v)}
          desc={desc}
          setDesc={setDesc}
          descApi={descApi}
          disabled={!modelCode}
          onOpen={openSection}
        />
      </section>

      <TwoPanelWorkspace
        section={detail.section}
        diagramBlob={detail.diagramBlob}
        diagramError={detail.diagramError}
        loadingDiagram={detail.loadingDiagram}
        items={detail.items}
        itemsError={detail.itemsError}
        loadingItems={detail.loadingItems}
        isSuperadmin={diagramReplace.isSuperadmin}
        uploading={diagramReplace.uploading}
        uploadError={diagramReplace.uploadError}
        fileInputRef={diagramReplace.fileInputRef}
        onUploadClick={diagramReplace.onUploadClick}
        onFileChange={diagramReplace.onFileChange}
      />
    </AdminLayout>
  );
}
