'use client';
import { useState, useEffect, useCallback } from 'react';
import AdminLayout from '../admin-layout';
import { authFetch } from '../../lib/authFetch';
import { Search, ChevronLeft, ChevronRight, X, ArrowUp, ArrowDown, ChevronsUpDown, AlertTriangle, CheckCircle2, ShieldX, Pencil, UploadCloud, BarChart3, Download, Flag, Trash2 } from 'lucide-react';

const PAGE_SIZE = 50;

const computeImpliedProviderMargin = (priceCOP, costoCOP, factors) => {
  if (!priceCOP || !costoCOP || !factors) return null;
  const K = (1 + factors.distributor_margin) * (1 + factors.iva_rate);
  const impliedDist = priceCOP / K;
  const margin = (impliedDist / (costoCOP * (1 + factors.iva_rate))) - 1;
  return margin;
};

const marginColor = (m) =>
  m == null ? null : m >= 0.30 ? '#4ade80' : m >= 0.10 ? '#facc15' : m >= 0 ? '#fb923c' : '#ef4444';

const ROTATION_STYLES = {
  alta:  { bg: 'rgba(239,68,68,0.12)',  color: '#ef4444', border: 'rgba(239,68,68,0.3)' },
  media: { bg: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: 'rgba(251,191,36,0.3)' },
  baja:  { bg: 'rgba(74,222,128,0.12)', color: '#4ade80', border: 'rgba(74,222,128,0.3)' },
};
const rotationBadge = (rc) => {
  const c = ROTATION_STYLES[rc] || { bg: 'rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.3)', border: 'rgba(255,255,255,0.1)' };
  return { fontSize: '0.58rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.08em', padding: '2px 8px', borderRadius: '20px', background: c.bg, color: c.color, border: `1px solid ${c.border}`, display: 'inline-block', whiteSpace: 'nowrap' };
};

export default function PartsCatalogPage() {
  const [items, setItems]     = useState([]);
  const [total, setTotal]     = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage]       = useState(1);

  const [search, setSearch]           = useState('');
  const [searchInput, setSearchInput] = useState('');

  useEffect(() => {
    const t = setTimeout(() => { setSearch(searchInput); setPage(1); }, 150);
    return () => clearTimeout(t);
  }, [searchInput]);
  const [modelCode, setModelCode]     = useState('');
  const [models, setModels]           = useState([]);
  const [onlyPending, setOnlyPending] = useState(false);
  const [onlyPriceReview, setOnlyPriceReview] = useState(false);
  const [rotationFilter, setRotationFilter] = useState('');
  const [coverageFilter, setCoverageFilter] = useState('');

  const [sortCol, setSortCol] = useState('section_code');
  const [sortDir, setSortDir] = useState('asc');

  // Modal de verificación
  const [reviewTask, setReviewTask] = useState(null); // { taskId, existingCode, candidateCode, score }
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewMsg, setReviewMsg] = useState('');

  // Modal de edición
  const [editItem, setEditItem] = useState(null);
  const EMPTY_SUB = { substitute_part_code: '', brand: '', model: '' };
  const [editForm, setEditForm] = useState({ description: '', description_es_manual: '', public_price: '', rotation_class: '', substitutes: [{ ...EMPTY_SUB }, { ...EMPTY_SUB }, { ...EMPTY_SUB }], prev_codes: [] });
  const [newPrevCode, setNewPrevCode] = useState('');
  const [editLoading, setEditLoading] = useState(false);
  const [editMsg, setEditMsg] = useState('');

  // Modal de confirmación de eliminación
  const [deleteItem, setDeleteItem] = useState(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  // Modal de carga masiva de rotación
  const [showRotationUpload, setShowRotationUpload] = useState(false);
  const [rotationFile, setRotationFile] = useState(null);
  const [rotationUploading, setRotationUploading] = useState(false);
  const [rotationResult, setRotationResult] = useState(null);

  // Backfill de costos
  const [backfilling, setBackfilling] = useState(false);
  const [backfillResult, setBackfillResult] = useState(null);

  const handleBackfillCosts = async () => {
    setBackfilling(true);
    setBackfillResult(null);
    try {
      const res = await authFetch('/parts/admin/backfill-costs', { method: 'POST' });
      const data = await res.json();
      setBackfillResult(data);
      fetchData();
    } catch { setBackfillResult({ error: 'Error de conexión' }); }
    finally { setBackfilling(false); }
  };

  // Panel de cobertura
  const [coverage, setCoverage] = useState(null);

  const [pricingFactors, setPricingFactors] = useState(null);

  useEffect(() => {
    authFetch('/parts/admin/vehicle-models')
      .then(r => r.ok ? r.json() : [])
      .then(data => setModels((Array.isArray(data) ? data : []).filter(m => m.catalog_model_code)))
      .catch(() => {});
  }, []);

  useEffect(() => {
    authFetch('/settings/pricing-factors')
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setPricingFactors(data); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const qs = modelCode ? `?model_code=${encodeURIComponent(modelCode)}` : '';
    authFetch(`/parts/admin/coverage${qs}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setCoverage(data); })
      .catch(() => {});
  }, [modelCode]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(PAGE_SIZE),
        search,
        model_code: modelCode,
        only_pending: String(onlyPending),
        only_price_review: String(onlyPriceReview),
        rotation_class: rotationFilter,
        coverage_status: coverageFilter,
        sort_col: sortCol,
        sort_dir: sortDir,
      });
      const res = await authFetch(`/parts/admin/catalog?${params}`);
      if (res.ok) {
        const data = await res.json();
        setItems(data.items || []);
        setTotal(data.total || 0);
      } else {
        const errText = await res.text().catch(() => '');
        console.error('[catalog] error', res.status, errText, params.toString());
      }
    } catch (e) {
      console.error('[catalog] exception', e);
    } finally {
      setLoading(false);
    }
  }, [page, search, modelCode, onlyPending, onlyPriceReview, rotationFilter, coverageFilter, sortCol, sortDir]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const totalPages = Math.ceil(total / PAGE_SIZE);

  const clearSearch = () => { setSearchInput(''); setPage(1); };

  const PRICE_COLS = ['avg_fob_cost', 'public_price'];
  const toggleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir(PRICE_COLS.includes(col) ? 'desc' : 'asc'); }
    setPage(1);
  };
  const SortIcon = ({ col }) => sortCol === col
    ? (sortDir === 'asc'
        ? <ArrowUp size={10} style={{ color: '#ff5f33', marginLeft: '3px', flexShrink: 0 }} />
        : <ArrowDown size={10} style={{ color: '#ff5f33', marginLeft: '3px', flexShrink: 0 }} />)
    : <ChevronsUpDown size={10} style={{ opacity: 0.25, marginLeft: '3px', flexShrink: 0 }} />;

  // Sort is server-side — items already arrive ordered from the backend
  const sortedItems = items;

  const pendingCount = items.filter(i => i.pending_task_id).length;

  const openReview = (item) => {
    setReviewMsg('');
    setReviewTask({
      taskId: item.pending_task_id,
      existingCode: item.factory_part_number,
      candidateCode: item.pending_candidate_code,
      score: item.pending_score,
      description: item.description,
    });
  };

  const handleReviewAction = async (action) => {
    if (!reviewTask) return;
    setReviewLoading(true);
    setReviewMsg('');
    try {
      const res = await authFetch(`/parts/admin/review-tasks/${reviewTask.taskId}/${action}`, { method: 'POST' });
      if (res.ok) {
        setReviewMsg(action === 'approve' ? '✅ Código actualizado.' : '✅ Sugerencia descartada.');
        setTimeout(() => { setReviewTask(null); fetchData(); }, 1200);
      } else {
        const err = await res.json().catch(() => ({}));
        setReviewMsg(`⚠️ ${err.detail || 'Error al procesar.'}`);
      }
    } catch { setReviewMsg('⚠️ Error de conexión.'); }
    finally { setReviewLoading(false); }
  };

  const togglePriceReview = async (item) => {
    const newVal = !item.needs_price_review;
    await authFetch(`/parts/admin/catalog/${encodeURIComponent(item.factory_part_number)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ needs_price_review: newVal }),
    });
    fetchData();
  };

  const updateRotation = async (item, rc) => {
    const newVal = item.rotation_class === rc ? null : rc;
    setItems(prev => prev.map(i => i.factory_part_number === item.factory_part_number ? { ...i, rotation_class: newVal } : i));
    await authFetch(`/parts/admin/catalog/${encodeURIComponent(item.factory_part_number)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rotation_class: newVal }),
    });
  };

  const openEdit = (item) => {
    setEditMsg('');
    const defaultPrice = item.public_price != null
      ? String(item.public_price)
      : item.precio_publico_calculado != null
        ? String(Math.round(Number(item.precio_publico_calculado)))
        : '';
    const existingSubs = Array.isArray(item.substitutes) ? item.substitutes : [];
    const substitutes = [0, 1, 2].map(i => existingSubs[i]
      ? { substitute_part_code: existingSubs[i].substitute_part_code, brand: existingSubs[i].brand, model: existingSubs[i].model }
      : { ...EMPTY_SUB }
    );
    setNewPrevCode('');
    setEditForm({
      description: item.description || '',
      description_es_manual: item.description_es || '',
      public_price: defaultPrice,
      rotation_class: item.rotation_class || '',
      substitutes,
      prev_codes: Array.isArray(item.prev_codes) ? [...item.prev_codes] : [],
    });
    setEditItem(item);
  };

  const handleEditSave = async () => {
    if (!editItem) return;
    setEditLoading(true);
    setEditMsg('');
    try {
      const body = {};
      if (editForm.description.trim()) body.description = editForm.description.trim();
      body.description_es_manual = editForm.description_es_manual.trim() || null;
      const price = parseFloat(editForm.public_price);
      if (!isNaN(price) && price > 0) body.public_price = price;
      body.substitutes = editForm.substitutes.filter(s => s.substitute_part_code.trim() && s.brand.trim() && s.model.trim());
      body.rotation_class = editForm.rotation_class || null;
      body.prev_codes = editForm.prev_codes.filter(c => c.trim());
      const res = await authFetch(`/parts/admin/catalog/${encodeURIComponent(editItem.factory_part_number)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        setEditMsg('✅ Guardado.');
        setTimeout(() => { setEditItem(null); fetchData(); }, 900);
      } else {
        const err = await res.json().catch(() => ({}));
        setEditMsg(`⚠️ ${err.detail || 'Error al guardar.'}`);
      }
    } catch { setEditMsg('⚠️ Error de conexión.'); }
    finally { setEditLoading(false); }
  };

  const handleDeletePart = async () => {
    if (!deleteItem) return;
    setDeleteLoading(true);
    setDeleteError('');
    try {
      const res = await authFetch(`/parts/admin/catalog/part/${encodeURIComponent(deleteItem.factory_part_number)}`, { method: 'DELETE' });
      if (res.ok || res.status === 204) {
        setDeleteItem(null);
        fetchData();
      } else {
        const err = await res.json().catch(() => ({}));
        setDeleteError(err.detail || 'Error al eliminar.');
      }
    } catch { setDeleteError('Error de conexión.'); }
    finally { setDeleteLoading(false); }
  };

  const handleRotationImport = async () => {
    if (!rotationFile) return;
    setRotationUploading(true);
    setRotationResult(null);
    try {
      const fd = new FormData();
      fd.append('file', rotationFile);
      const res = await authFetch('/parts/admin/rotation-import', { method: 'POST', body: fd });
      const data = await res.json();
      setRotationResult(data);
      fetchData();
      const qs = modelCode ? `?model_code=${encodeURIComponent(modelCode)}` : '';
      authFetch(`/parts/admin/coverage${qs}`).then(r => r.ok ? r.json() : null).then(d => { if (d) setCoverage(d); }).catch(() => {});
    } catch { setRotationResult({ error: 'Error de conexión' }); }
    finally { setRotationUploading(false); }
  };

  return (
    <AdminLayout>
      <header className="page-header">
        <div>
          <h1 className="page-title">Maestro de <span style={{ fontStyle: 'italic', color: 'var(--accent-orange)', WebkitTextFillColor: 'var(--accent-orange)' }}>Partes</span></h1>
          <p className="page-subtitle">
            {total > 0 ? `${total.toLocaleString()} repuestos cargados en el sistema` : 'Consulta el catálogo de despiece de todos los modelos'}
            {pendingCount > 0 && !onlyPending && (
              <span style={{ marginLeft: '0.75rem', fontSize: '0.68rem', fontWeight: 800, padding: '2px 10px', borderRadius: '20px', background: 'rgba(251,146,60,0.15)', color: '#fb923c', border: '1px solid rgba(251,146,60,0.3)', cursor: 'pointer' }}
                onClick={() => { setOnlyPending(true); setPage(1); }}>
                {pendingCount} pendiente{pendingCount > 1 ? 's' : ''} de verificación
              </span>
            )}
          </p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.4rem' }}>
          <button
            onClick={() => { setShowRotationUpload(true); setRotationFile(null); setRotationResult(null); }}
            style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.6rem 1.1rem', borderRadius: '10px', background: 'rgba(99,102,241,0.12)', border: '1px solid rgba(99,102,241,0.3)', color: '#818cf8', fontSize: '0.72rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em', cursor: 'pointer', flexShrink: 0 }}
          >
            <UploadCloud size={14} /> Clasificar rotación
          </button>
          <button
            onClick={handleBackfillCosts}
            disabled={backfilling}
            style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.9rem', borderRadius: '10px', background: 'rgba(56,189,248,0.08)', border: '1px solid rgba(56,189,248,0.25)', color: '#38bdf8', fontSize: '0.65rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em', cursor: backfilling ? 'not-allowed' : 'pointer', flexShrink: 0, opacity: backfilling ? 0.5 : 1 }}
          >
            <BarChart3 size={12} /> {backfilling ? 'Calculando...' : 'Recalcular costos'}
          </button>
          {backfillResult && !backfillResult.error && (
            <span style={{ fontSize: '0.6rem', color: '#4ade80', fontWeight: 700 }}>
              ✓ {backfillResult.updated} de {backfillResult.checked} actualizados
            </span>
          )}
          {backfillResult?.error && (
            <span style={{ fontSize: '0.6rem', color: '#ef4444', fontWeight: 700 }}>⚠ {backfillResult.error}</span>
          )}
        </div>
      </header>

      {/* Panel de cobertura por rotación */}
      {coverage && (coverage.buckets?.length > 0 || coverage.sin_clasificar > 0) && (
        <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
          {coverage.buckets.map(b => {
            const c = ROTATION_STYLES[b.rotation_class] || {};
            return (
              <div key={b.rotation_class} style={{ flex: '1 1 180px', background: 'rgba(255,255,255,0.02)', border: `1px solid ${c.border || 'rgba(255,255,255,0.08)'}`, borderRadius: '12px', padding: '0.875rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={rotationBadge(b.rotation_class)}>{b.rotation_class}</span>
                  <span style={{ fontSize: '0.62rem', color: 'rgba(255,255,255,0.3)', fontWeight: 600 }}>{b.total} partes</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                  {[
                    { label: 'Aquí',       val: b.aqui,       pct: b.pct_aqui,       color: '#4ade80' },
                    { label: 'En camino',  val: b.en_camino,  pct: b.pct_en_camino,  color: '#38bdf8' },
                    { label: 'Pedido',     val: b.pedido,     pct: b.pct_pedido,     color: '#a78bfa' },
                    { label: 'No pedidas', val: b.no_pedidas, pct: b.pct_no_pedidas, color: '#ef4444' },
                  ].map(({ label, val, pct, color }) => (
                    <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <span style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.35)', width: '64px', flexShrink: 0 }}>{label}</span>
                      <div style={{ flex: 1, height: '4px', borderRadius: '2px', background: 'rgba(255,255,255,0.05)' }}>
                        <div style={{ height: '100%', width: `${Math.min(pct, 100)}%`, borderRadius: '2px', background: color, transition: 'width 0.4s' }} />
                      </div>
                      <span style={{ fontSize: '0.6rem', fontWeight: 700, color, width: '38px', textAlign: 'right', flexShrink: 0 }}>{val} <span style={{ fontWeight: 400, opacity: 0.6 }}>({pct.toFixed(0)}%)</span></span>
                    </div>
                  ))}
                </div>
                <button
                  onClick={async () => {
                    const res = await authFetch(`/parts/admin/coverage/unordered?rotation_class=${b.rotation_class}`);
                    if (!res.ok) return;
                    const blob = await res.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a'); a.href = url; a.download = `no_pedidas_${b.rotation_class}.xlsx`; a.click(); URL.revokeObjectURL(url);
                  }}
                  style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.58rem', fontWeight: 700, color: 'rgba(255,255,255,0.3)', background: 'none', border: 'none', cursor: 'pointer', marginTop: '0.1rem', padding: 0 }}
                >
                  <Download size={9} /> Exportar no pedidas
                </button>
              </div>
            );
          })}
          {coverage.sin_clasificar > 0 && (
            <div style={{ flex: '1 1 140px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '12px', padding: '0.875rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.3rem', justifyContent: 'center' }}>
              <span style={{ fontSize: '0.58rem', fontWeight: 800, color: 'rgba(255,255,255,0.25)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Sin clasificar</span>
              <span style={{ fontSize: '1.1rem', fontWeight: 900, color: 'rgba(255,255,255,0.35)', fontFamily: 'monospace' }}>{coverage.sin_clasificar.toLocaleString()}</span>
            </div>
          )}
        </div>
      )}

      {/* Barra de filtros */}
      <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.25rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: '0.5rem', flex: '1 1 280px', minWidth: 0 }}>
          <div style={{ flex: 1, position: 'relative', minWidth: 0 }}>
            <Search size={14} color="rgba(255,255,255,0.25)" style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
            <input
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
              placeholder="Buscar por código fábrica, código UM, descripción..."
              style={{ width: '100%', padding: '0.625rem 2.25rem 0.625rem 2.25rem', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '10px', color: '#fff', fontSize: '0.78rem', outline: 'none', boxSizing: 'border-box' }}
            />
            {searchInput && (
              <button type="button" onClick={clearSearch} style={{ position: 'absolute', right: '0.625rem', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: 'rgba(255,255,255,0.3)', cursor: 'pointer', display: 'flex', padding: 0 }}>
                <X size={13} />
              </button>
            )}
          </div>
        </div>

        <select
          value={modelCode}
          onChange={e => { setModelCode(e.target.value); setPage(1); }}
          style={{ padding: '0.625rem 1rem', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '10px', color: modelCode ? '#fff' : 'rgba(255,255,255,0.3)', fontSize: '0.78rem', outline: 'none', cursor: 'pointer', flexShrink: 0 }}
        >
          <option value="">Todos los modelos</option>
          {models.map(m => <option key={m.vehicle_model} value={m.catalog_model_code}>{m.vehicle_model}</option>)}
        </select>

        <select
          value={rotationFilter}
          onChange={e => { setRotationFilter(e.target.value); setPage(1); }}
          style={{ padding: '0.625rem 1rem', background: rotationFilter ? (ROTATION_STYLES[rotationFilter]?.bg || 'rgba(255,255,255,0.04)') : 'rgba(255,255,255,0.04)', border: `1px solid ${rotationFilter ? (ROTATION_STYLES[rotationFilter]?.border || 'rgba(255,255,255,0.08)') : 'rgba(255,255,255,0.08)'}`, borderRadius: '10px', color: rotationFilter ? (ROTATION_STYLES[rotationFilter]?.color || '#fff') : 'rgba(255,255,255,0.3)', fontSize: '0.78rem', outline: 'none', cursor: 'pointer', flexShrink: 0, fontWeight: rotationFilter ? 800 : 400 }}
        >
          <option value="">Toda rotación</option>
          <option value="alta">Alta rotación</option>
          <option value="media">Media rotación</option>
          <option value="baja">Baja rotación</option>
          <option value="none">Sin clasificar</option>
        </select>

        <div style={{ position: 'relative', display: 'inline-block' }}
          onMouseEnter={e => { const t = e.currentTarget.querySelector('[data-tip]'); if (t) t.style.opacity = '1'; }}
          onMouseLeave={e => { const t = e.currentTarget.querySelector('[data-tip]'); if (t) t.style.opacity = '0'; }}
        >
          <button
            onClick={() => { setOnlyPending(p => !p); setPage(1); }}
            style={{ padding: '0.625rem 1rem', borderRadius: '10px', fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', cursor: 'pointer', border: '1px solid', transition: 'all 0.2s',
              background: onlyPending ? 'rgba(251,146,60,0.15)' : 'rgba(255,255,255,0.04)',
              borderColor: onlyPending ? 'rgba(251,146,60,0.4)' : 'rgba(255,255,255,0.08)',
              color: onlyPending ? '#fb923c' : 'rgba(255,255,255,0.5)',
            }}
          >
            <AlertTriangle size={12} style={{ display: 'inline', marginRight: '0.4rem', verticalAlign: 'middle' }} />
            {onlyPending ? 'Mostrando pendientes' : 'Solo pendientes'}
          </button>
          <button
            onClick={() => { setOnlyPriceReview(p => !p); setPage(1); }}
            style={{ padding: '0.625rem 1rem', borderRadius: '10px', fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', cursor: 'pointer', border: '1px solid', transition: 'all 0.2s',
              background: onlyPriceReview ? 'rgba(234,179,8,0.15)' : 'rgba(255,255,255,0.04)',
              borderColor: onlyPriceReview ? 'rgba(234,179,8,0.4)' : 'rgba(255,255,255,0.08)',
              color: onlyPriceReview ? '#eab308' : 'rgba(255,255,255,0.5)',
            }}
          >
            <Flag size={12} style={{ display: 'inline', marginRight: '0.4rem', verticalAlign: 'middle' }} />
            {onlyPriceReview ? 'Revisar precio' : 'Revisar precio'}
          </button>
          {[
            { val: 'aqui',       label: 'Aquí',       color: '#4ade80' },
            { val: 'en_camino',  label: 'En camino',  color: '#38bdf8' },
            { val: 'pedido',     label: 'Pedido',     color: '#a78bfa' },
            { val: 'no_pedidas', label: 'No pedidas', color: '#ef4444' },
          ].map(({ val, label, color }) => {
            const active = coverageFilter === val;
            return (
              <button key={val}
                onClick={() => { setCoverageFilter(active ? '' : val); setPage(1); }}
                style={{ padding: '0.625rem 1rem', borderRadius: '10px', fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', cursor: 'pointer', border: '1px solid', transition: 'all 0.2s',
                  background: active ? `${color}22` : 'rgba(255,255,255,0.04)',
                  borderColor: active ? `${color}66` : 'rgba(255,255,255,0.08)',
                  color: active ? color : 'rgba(255,255,255,0.5)',
                }}
              >{label}</button>
            );
          })}
          <div data-tip style={{
            position: 'absolute', bottom: 'calc(100% + 8px)', right: 0,
            background: '#16161f', border: '1px solid rgba(251,146,60,0.25)',
            borderRadius: '8px', padding: '7px 11px', width: 230,
            fontSize: '10px', lineHeight: '1.5', color: '#9ca3af',
            pointerEvents: 'none', opacity: 0, transition: 'opacity 0.15s',
            boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
            zIndex: 50,
          }}>
            <span style={{ color: '#fb923c', fontWeight: 700, display: 'block', marginBottom: 3 }}>
              <AlertTriangle size={10} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
              Revisión de código pendiente
            </span>
            Partes donde el sistema detectó un posible código duplicado o equivalente sin verificar.
            <div style={{
              position: 'absolute', bottom: -5, right: 18,
              width: 8, height: 8, background: '#16161f',
              border: '1px solid rgba(251,146,60,0.25)',
              borderTop: 'none', borderLeft: 'none',
              transform: 'rotate(45deg)',
            }} />
          </div>
        </div>
      </div>

      {/* Tabla */}
      <div className="glass table-scroll-wrapper rounded-2xl border border-white/5 shadow-2xl">
        <table className="master-table">
          <thead>
            <tr>
              {[
                ['factory_part_number', 'Ref. Fábrica'],
                ['description',         'Descripción'],
                ['description_es',      'Descripción ES'],
                ['vehicle_model_name',  'Modelo'],
              ].map(([col, lbl]) => (
                <th key={col} onClick={() => toggleSort(col)} className="sort-head">
                  {lbl} <SortIcon col={col} />
                </th>
              ))}
              <th className="sort-head" onClick={() => toggleSort('rotation_class')} style={{ whiteSpace: 'nowrap' }}>Rotación <SortIcon col="rotation_class" /></th>
              <th className="sort-head" onClick={() => toggleSort('avg_fob_cost')} style={{ whiteSpace: 'nowrap' }}>FOB Prom. <span style={{ fontWeight: 400, opacity: 0.5 }}>USD</span> <SortIcon col="avg_fob_cost" /></th>
              <th className="sort-head" onClick={() => toggleSort('avg_fob_cost')} style={{ whiteSpace: 'nowrap' }}>C. Importado <span style={{ fontWeight: 400, opacity: 0.5 }}>COP</span> <SortIcon col="avg_fob_cost" /></th>
              <th className="sort-head" onClick={() => toggleSort('avg_fob_cost')} style={{ whiteSpace: 'nowrap' }}>P. Distribuidor <span style={{ fontWeight: 400, opacity: 0.5 }}>COP</span> <SortIcon col="avg_fob_cost" /></th>
              <th className="sort-head" onClick={() => toggleSort('avg_fob_cost')} style={{ whiteSpace: 'nowrap' }}>P. Público Calc. <span style={{ fontWeight: 400, opacity: 0.5 }}>COP</span> <SortIcon col="avg_fob_cost" /></th>
              <th className="sort-head" onClick={() => toggleSort('public_price')} style={{ whiteSpace: 'nowrap' }}>Precio Final <SortIcon col="public_price" /></th>
              <th className="sort-head" onClick={() => toggleSort('needs_price_review')} style={{ whiteSpace: 'nowrap', textAlign: 'center' }} title="Revisar precio"><Flag size={12} style={{ display: 'inline', verticalAlign: 'middle' }} /> <SortIcon col="needs_price_review" /></th>
              <th className="sort-head" style={{ width: '90px', textAlign: 'center' }}>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="12" style={{ textAlign: 'center', padding: '3rem', color: 'rgba(255,255,255,0.3)', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Cargando repuestos...</td></tr>
            ) : sortedItems.length === 0 ? (
              <tr><td colSpan="12" style={{ textAlign: 'center', padding: '4rem', color: 'rgba(255,255,255,0.2)', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                {!search && !modelCode && !onlyPending ? 'Sin repuestos cargados — subí los PDFs desde Configuración' : 'Sin resultados para la búsqueda'}
              </td></tr>
            ) : sortedItems.map((item, i) => (
              <tr key={`${item.factory_part_number}-${item.section_code}-${i}`} className="hover:bg-white/5 transition-colors border-b border-white/5">
                <td style={{ whiteSpace: 'nowrap' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    {(() => {
                      const DOT = { aqui: '#4ade80', en_camino: '#38bdf8', pedido: '#a78bfa', sin_pedido: '#ef4444' };
                      const TIP = { aqui: 'Aquí', en_camino: 'En camino', pedido: 'Pedido', sin_pedido: 'No pedida' };
                      return <span title={TIP[item.coverage_status] || 'No pedida'} style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: DOT[item.coverage_status] || DOT.sin_pedido, flexShrink: 0 }} />;
                    })()}
                    <span style={{ fontFamily: 'monospace', fontSize: '0.78rem', fontWeight: 700, color: '#ff5f33' }}>{item.factory_part_number}</span>
                  </div>
                </td>
                <td style={{ color: 'rgba(255,255,255,0.85)', maxWidth: '260px' }}>
                  <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.description || '—'}</span>
                </td>
                <td style={{ maxWidth: '220px' }}>
                  {item.description_es
                    ? <span style={{ color: '#4ade80', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.description_es}</span>
                    : <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: '0.68rem' }}>—</span>
                  }
                </td>
                <td><span className="cell-truncate" style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.7)', fontWeight: 600 }} title={item.vehicle_model_name || '—'}>{item.vehicle_model_name || '—'}</span></td>
                <td>
                  <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                    {[['alta','A','#ef4444'],['media','M','#fbbf24'],['baja','B','#4ade80']].map(([val, label, color]) => {
                      const active = item.rotation_class === val;
                      return (
                        <button key={val} onClick={() => updateRotation(item, val)} title={val}
                          style={{ width: 20, height: 20, borderRadius: '50%', border: `2px solid ${active ? color : 'rgba(255,255,255,0.15)'}`, background: active ? color : 'transparent', color: active ? '#000' : 'rgba(255,255,255,0.25)', fontSize: '0.52rem', fontWeight: 900, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0, lineHeight: 1, transition: 'all 0.15s' }}>
                          {label}
                        </button>
                      );
                    })}
                  </div>
                </td>
                <td>
                  {item.avg_fob_cost != null
                    ? <span style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.78rem', color: '#38bdf8' }}>${Number(item.avg_fob_cost).toFixed(2)}</span>
                    : <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: '0.68rem' }}>—</span>}
                </td>
                <td>
                  {item.costo_importado != null
                    ? <span style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.78rem', color: '#fb923c' }}>${Number(item.costo_importado).toLocaleString('es-CO', { maximumFractionDigits: 0 })}</span>
                    : <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: '0.68rem' }}>—</span>}
                </td>
                <td>
                  {item.precio_distribuidor != null
                    ? <span style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.78rem', color: '#facc15' }}>${Number(item.precio_distribuidor).toLocaleString('es-CO', { maximumFractionDigits: 0 })}</span>
                    : <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: '0.68rem' }}>—</span>}
                </td>
                <td>
                  {item.precio_publico_calculado != null
                    ? <span style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.78rem', color: '#4ade80' }}>${Number(item.precio_publico_calculado).toLocaleString('es-CO', { maximumFractionDigits: 0 })}</span>
                    : <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: '0.68rem' }}>—</span>}
                </td>
                <td>
                  {(() => {
                    const effectivePrice = item.public_price ?? item.precio_publico_calculado;
                    const isManual = item.public_price != null;
                    if (effectivePrice == null) return <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: '0.68rem' }}>—</span>;
                    const m = computeImpliedProviderMargin(effectivePrice, item.costo_importado, pricingFactors);
                    const mc = marginColor(m);
                    return (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                        <span style={{ fontFamily: 'monospace', fontWeight: isManual ? 800 : 700, fontSize: '0.78rem', color: isManual ? '#fff' : 'rgba(74,222,128,0.6)', fontStyle: isManual ? 'normal' : 'italic' }}>
                          ${Number(effectivePrice).toLocaleString('es-CO', { maximumFractionDigits: 0 })}
                        </span>
                        {m != null && (
                          <span style={{ fontSize: '0.58rem', fontWeight: 700, color: mc, letterSpacing: '0.02em' }}>
                            M.Prov {m >= 0 ? '+' : ''}{(m * 100).toFixed(1)}%
                          </span>
                        )}
                      </div>
                    );
                  })()}
                </td>
                <td style={{ textAlign: 'center' }}>
                  <button
                    onClick={() => togglePriceReview(item)}
                    title={item.needs_price_review ? 'Quitar marca de revisión' : 'Marcar para revisar precio'}
                    style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: '24px', height: '24px', borderRadius: '6px', cursor: 'pointer', transition: 'all 0.15s', border: 'none',
                      background: item.needs_price_review ? 'rgba(234,179,8,0.15)' : 'transparent',
                      color: item.needs_price_review ? '#eab308' : 'rgba(255,255,255,0.15)',
                    }}
                  >
                    <Flag size={12} />
                  </button>
                </td>
                <td style={{ textAlign: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                    {item.pending_task_id && (
                      <button
                        onClick={() => openReview(item)}
                        title="Verificar posible cambio de código"
                        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '26px', height: '26px', borderRadius: '8px', background: 'rgba(251,146,60,0.15)', color: '#fb923c', border: '1px solid rgba(251,146,60,0.35)', cursor: 'pointer', flexShrink: 0 }}
                      >
                        <AlertTriangle size={13} />
                      </button>
                    )}
                    <button
                      onClick={() => openEdit(item)}
                      title="Editar repuesto"
                      style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '26px', height: '26px', borderRadius: '8px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)', color: 'rgba(255,255,255,0.4)', cursor: 'pointer', transition: 'all 0.15s' }}
                      onMouseEnter={e => { e.currentTarget.style.background = 'rgba(99,102,241,0.15)'; e.currentTarget.style.color = '#818cf8'; e.currentTarget.style.borderColor = 'rgba(99,102,241,0.3)'; }}
                      onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.05)'; e.currentTarget.style.color = 'rgba(255,255,255,0.4)'; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)'; }}
                    >
                      <Pencil size={11} />
                    </button>
                    {item.avg_fob_cost == null && (
                      <button
                        onClick={() => { setDeleteError(''); setDeleteItem(item); }}
                        title="Eliminar repuesto"
                        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '26px', height: '26px', borderRadius: '8px', background: 'rgba(239,68,68,0.07)', border: '1px solid rgba(239,68,68,0.15)', color: 'rgba(239,68,68,0.45)', cursor: 'pointer', transition: 'all 0.15s' }}
                        onMouseEnter={e => { e.currentTarget.style.background = 'rgba(239,68,68,0.18)'; e.currentTarget.style.color = '#ef4444'; e.currentTarget.style.borderColor = 'rgba(239,68,68,0.4)'; }}
                        onMouseLeave={e => { e.currentTarget.style.background = 'rgba(239,68,68,0.07)'; e.currentTarget.style.color = 'rgba(239,68,68,0.45)'; e.currentTarget.style.borderColor = 'rgba(239,68,68,0.15)'; }}
                      >
                        <Trash2 size={11} />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Paginación */}
        {totalPages > 1 && (
          <div style={{ padding: '0.875rem 1.5rem', borderTop: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '0.68rem', color: '#9ca3af' }}>
              {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} de {total.toLocaleString()} repuestos
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                style={{ background: 'rgba(255,255,255,0.05)', border: 'none', borderRadius: '6px', padding: '5px 8px', cursor: page === 1 ? 'not-allowed' : 'pointer', color: page === 1 ? '#606075' : '#fff', display: 'flex', alignItems: 'center' }}>
                <ChevronLeft size={14} />
              </button>
              <span style={{ fontSize: '11px', color: '#9ca3af', padding: '5px 8px' }}>{page} / {totalPages}</span>
              <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
                style={{ background: 'rgba(255,255,255,0.05)', border: 'none', borderRadius: '6px', padding: '5px 8px', cursor: page >= totalPages ? 'not-allowed' : 'pointer', color: page >= totalPages ? '#606075' : '#fff', display: 'flex', alignItems: 'center' }}>
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modal de edición de repuesto */}
      {editItem && (
        <div onClick={() => !editLoading && setEditItem(null)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div onClick={e => e.stopPropagation()}
            style={{ background: '#0c0c0e', border: '1px solid rgba(99,102,241,0.25)', borderRadius: '16px', padding: '2rem', width: '100%', maxWidth: '480px', maxHeight: '90vh', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <Pencil size={16} color="#818cf8" />
              <p style={{ color: '#fff', fontWeight: 900, fontSize: '0.82rem', textTransform: 'uppercase', letterSpacing: '0.05em', margin: 0 }}>Editar repuesto</p>
              <span style={{ marginLeft: 'auto', fontFamily: 'monospace', fontSize: '0.72rem', color: '#ff5f33', fontWeight: 700 }}>{editItem.factory_part_number}</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.62rem', fontWeight: 800, color: 'rgba(255,255,255,0.35)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.4rem' }}>Descripción (inglés)</label>
                <input
                  value={editForm.description}
                  onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                  style={{ width: '100%', padding: '0.6rem 0.85rem', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: '#fff', fontSize: '0.78rem', outline: 'none', boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.62rem', fontWeight: 800, color: 'rgba(255,255,255,0.35)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.4rem' }}>Descripción ES</label>
                <input
                  value={editForm.description_es_manual}
                  onChange={e => setEditForm(f => ({ ...f, description_es_manual: e.target.value }))}
                  placeholder="Dejar vacío para usar la descripción de pedidos"
                  style={{ width: '100%', padding: '0.6rem 0.85rem', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: '#fff', fontSize: '0.78rem', outline: 'none', boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.62rem', fontWeight: 800, color: 'rgba(255,255,255,0.35)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.4rem' }}>Rotación</label>
                <select
                  value={editForm.rotation_class}
                  onChange={e => setEditForm(f => ({ ...f, rotation_class: e.target.value }))}
                  style={{ width: '100%', padding: '0.6rem 0.85rem', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: editForm.rotation_class ? '#fff' : 'rgba(255,255,255,0.3)', fontSize: '0.78rem', outline: 'none', boxSizing: 'border-box', cursor: 'pointer' }}
                >
                  <option value="">Sin clasificar</option>
                  <option value="alta">Alta</option>
                  <option value="media">Media</option>
                  <option value="baja">Baja</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.62rem', fontWeight: 800, color: 'rgba(255,255,255,0.35)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.4rem' }}>Precio Final (COP)</label>
                <input
                  type="number"
                  value={editForm.public_price}
                  onChange={e => setEditForm(f => ({ ...f, public_price: e.target.value }))}
                  placeholder="0"
                  style={{ width: '100%', padding: '0.6rem 0.85rem', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: '#fff', fontSize: '0.78rem', outline: 'none', boxSizing: 'border-box' }}
                />
                {(() => {
                  if (!pricingFactors || !editItem?.costo_importado) return null;
                  const price = parseFloat(editForm.public_price);
                  if (isNaN(price) || price <= 0) return null;
                  const m = computeImpliedProviderMargin(price, editItem.costo_importado, pricingFactors);
                  if (m == null) return null;
                  const mc = marginColor(m);
                  const isNeg = m < 0;
                  return (
                    <div style={{ marginTop: '0.4rem', padding: '0.4rem 0.65rem', borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: isNeg ? 'rgba(239,68,68,0.06)' : 'rgba(74,222,128,0.05)', border: `1px solid ${isNeg ? 'rgba(239,68,68,0.2)' : 'rgba(255,255,255,0.07)'}` }}>
                      <span style={{ fontSize: '0.62rem', color: 'rgba(255,255,255,0.35)', fontWeight: 600 }}>
                        {isNeg ? '⚠ Margen proveedor NEGATIVO' : 'Margen proveedor implícito'}
                      </span>
                      <span style={{ fontSize: '0.75rem', fontWeight: 900, color: mc, fontFamily: 'monospace' }}>
                        {m >= 0 ? '+' : ''}{(m * 100).toFixed(1)}%
                      </span>
                    </div>
                  );
                })()}
              </div>

              <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '1rem', marginTop: '0.25rem' }}>
                <label style={{ display: 'block', fontSize: '0.62rem', fontWeight: 800, color: 'rgba(167,139,250,0.7)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.6rem' }}>
                  Códigos de fábrica relacionados <span style={{ fontWeight: 400, color: 'rgba(255,255,255,0.25)', textTransform: 'none', letterSpacing: 0 }}>— hasta 5</span>
                </label>
                {editForm.prev_codes.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginBottom: '0.6rem' }}>
                    {editForm.prev_codes.map((code, idx) => (
                      <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', padding: '0.25rem 0.5rem 0.25rem 0.65rem', background: 'rgba(167,139,250,0.08)', border: '1px solid rgba(167,139,250,0.2)', borderRadius: '6px' }}>
                        <span style={{ fontFamily: 'monospace', fontSize: '0.72rem', color: 'rgba(167,139,250,0.9)' }}>{code}</span>
                        <button
                          onClick={() => setEditForm(f => ({ ...f, prev_codes: f.prev_codes.filter((_, i) => i !== idx) }))}
                          style={{ display: 'flex', alignItems: 'center', background: 'none', border: 'none', cursor: 'pointer', padding: '1px', color: 'rgba(167,139,250,0.4)', lineHeight: 1 }}
                          title="Quitar"
                        >
                          <X size={11} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                {editForm.prev_codes.length < 5 && (
                  <div style={{ display: 'flex', gap: '0.4rem' }}>
                    <input
                      value={newPrevCode}
                      onChange={e => setNewPrevCode(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          const val = newPrevCode.trim();
                          if (val && !editForm.prev_codes.includes(val) && val !== editItem?.factory_part_number && editForm.prev_codes.length < 5) {
                            setEditForm(f => ({ ...f, prev_codes: [...f.prev_codes, val] }));
                            setNewPrevCode('');
                          }
                        }
                      }}
                      placeholder="Código a agregar"
                      style={{ flex: 1, padding: '0.5rem 0.65rem', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(167,139,250,0.2)', borderRadius: '6px', color: '#fff', fontSize: '0.72rem', fontFamily: 'monospace', outline: 'none', boxSizing: 'border-box' }}
                    />
                    <button
                      onClick={() => {
                        const val = newPrevCode.trim();
                        if (val && !editForm.prev_codes.includes(val) && val !== editItem?.factory_part_number && editForm.prev_codes.length < 5) {
                          setEditForm(f => ({ ...f, prev_codes: [...f.prev_codes, val] }));
                          setNewPrevCode('');
                        }
                      }}
                      style={{ padding: '0.5rem 0.75rem', background: 'rgba(167,139,250,0.12)', border: '1px solid rgba(167,139,250,0.25)', borderRadius: '6px', color: '#a78bfa', fontSize: '0.68rem', fontWeight: 800, cursor: 'pointer', whiteSpace: 'nowrap' }}
                    >
                      Agregar
                    </button>
                  </div>
                )}
                {editForm.prev_codes.length >= 5 && (
                  <p style={{ fontSize: '0.62rem', color: 'rgba(255,255,255,0.3)', margin: '0.3rem 0 0' }}>Límite de 5 códigos alcanzado.</p>
                )}
              </div>

              <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '1rem', marginTop: '0.25rem' }}>
                <label style={{ display: 'block', fontSize: '0.62rem', fontWeight: 800, color: 'rgba(129,140,248,0.7)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.75rem' }}>
                  Repuestos sustitutos <span style={{ fontWeight: 400, color: 'rgba(255,255,255,0.25)', textTransform: 'none', letterSpacing: 0 }}>— hasta 3</span>
                </label>
                {[0, 1, 2].map(idx => (
                  <div key={idx} style={{ marginBottom: idx < 2 ? '0.75rem' : 0, padding: '0.75rem', borderRadius: '8px', background: 'rgba(99,102,241,0.04)', border: '1px solid rgba(99,102,241,0.1)' }}>
                    <p style={{ fontSize: '0.58rem', fontWeight: 800, color: 'rgba(99,102,241,0.5)', textTransform: 'uppercase', letterSpacing: '0.08em', margin: '0 0 0.5rem' }}>Sustituto #{idx + 1}</p>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '0.5rem' }}>
                      <input
                        value={editForm.substitutes[idx].substitute_part_code}
                        onChange={e => setEditForm(f => { const subs = [...f.substitutes]; subs[idx] = { ...subs[idx], substitute_part_code: e.target.value }; return { ...f, substitutes: subs }; })}
                        placeholder="Código de parte"
                        style={{ padding: '0.5rem 0.65rem', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '6px', color: '#fff', fontSize: '0.72rem', fontFamily: 'monospace', outline: 'none', boxSizing: 'border-box' }}
                      />
                      <input
                        value={editForm.substitutes[idx].brand}
                        onChange={e => setEditForm(f => { const subs = [...f.substitutes]; subs[idx] = { ...subs[idx], brand: e.target.value }; return { ...f, substitutes: subs }; })}
                        placeholder="Marca"
                        style={{ padding: '0.5rem 0.65rem', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '6px', color: '#fff', fontSize: '0.72rem', outline: 'none', boxSizing: 'border-box' }}
                      />
                    </div>
                    <input
                      value={editForm.substitutes[idx].model}
                      onChange={e => setEditForm(f => { const subs = [...f.substitutes]; subs[idx] = { ...subs[idx], model: e.target.value }; return { ...f, substitutes: subs }; })}
                      placeholder="Modelo de motocicleta"
                      style={{ width: '100%', padding: '0.5rem 0.65rem', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '6px', color: '#fff', fontSize: '0.72rem', outline: 'none', boxSizing: 'border-box' }}
                    />
                  </div>
                ))}
              </div>
            </div>

            {editMsg && (
              <p style={{ fontSize: '0.72rem', color: editMsg.startsWith('✅') ? '#4ade80' : '#ef4444', margin: 0, textAlign: 'center' }}>{editMsg}</p>
            )}

            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button
                onClick={handleEditSave}
                disabled={editLoading}
                style={{ flex: 1, background: 'rgba(99,102,241,0.15)', color: '#818cf8', border: '1px solid rgba(99,102,241,0.3)', borderRadius: '10px', padding: '0.7rem', fontWeight: 900, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.06em', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem', opacity: editLoading ? 0.5 : 1 }}
              >
                <CheckCircle2 size={14} /> Guardar
              </button>
              <button
                onClick={() => setEditItem(null)}
                disabled={editLoading}
                style={{ flex: 1, background: 'rgba(255,255,255,0.03)', color: 'rgba(255,255,255,0.4)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '10px', padding: '0.7rem', fontWeight: 900, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.06em', cursor: 'pointer', opacity: editLoading ? 0.5 : 1 }}
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal de carga masiva de clasificación de rotación */}
      {showRotationUpload && (
        <div onClick={() => !rotationUploading && setShowRotationUpload(false)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div onClick={e => e.stopPropagation()}
            style={{ background: '#0c0c0e', border: '1px solid rgba(99,102,241,0.25)', borderRadius: '16px', padding: '2rem', width: '100%', maxWidth: '440px', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <UploadCloud size={16} color="#818cf8" />
              <p style={{ color: '#fff', fontWeight: 900, fontSize: '0.82rem', textTransform: 'uppercase', letterSpacing: '0.05em', margin: 0 }}>Clasificar rotación desde Excel</p>
            </div>

            <p style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.35)', margin: 0, lineHeight: 1.6 }}>
              El Excel debe tener columnas <strong style={{ color: 'rgba(255,255,255,0.6)' }}>part_code</strong> y <strong style={{ color: 'rgba(255,255,255,0.6)' }}>rotation_class</strong> (valores: alta, media, baja).
            </p>

            <label style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', padding: '1.5rem', borderRadius: '10px', border: `2px dashed ${rotationFile ? 'rgba(99,102,241,0.4)' : 'rgba(255,255,255,0.1)'}`, background: rotationFile ? 'rgba(99,102,241,0.05)' : 'rgba(255,255,255,0.02)', cursor: 'pointer', transition: 'all 0.2s' }}>
              <BarChart3 size={22} color={rotationFile ? '#818cf8' : 'rgba(255,255,255,0.2)'} />
              <span style={{ fontSize: '0.72rem', color: rotationFile ? '#818cf8' : 'rgba(255,255,255,0.3)', fontWeight: 600 }}>
                {rotationFile ? rotationFile.name : 'Seleccionar archivo .xlsx'}
              </span>
              <input type="file" accept=".xlsx" style={{ display: 'none' }} onChange={e => { setRotationFile(e.target.files[0] || null); setRotationResult(null); }} />
            </label>

            {rotationResult && !rotationResult.error && rotationResult.updated > 0 && (
              <div style={{ background: 'rgba(74,222,128,0.05)', border: '1px solid rgba(74,222,128,0.2)', borderRadius: '10px', padding: '0.875rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                <p style={{ margin: 0, fontSize: '0.72rem', fontWeight: 700, color: '#4ade80' }}>✅ Clasificación cargada</p>
                <p style={{ margin: 0, fontSize: '0.68rem', color: 'rgba(255,255,255,0.45)' }}>
                  Actualizadas: <strong style={{ color: '#fff' }}>{rotationResult.updated}</strong> &nbsp;·&nbsp;
                  Saltadas: <strong style={{ color: '#fb923c' }}>{rotationResult.skipped}</strong>
                  {rotationResult.errors?.length > 0 && <> &nbsp;·&nbsp; Con error: <strong style={{ color: '#ef4444' }}>{rotationResult.errors.length}</strong></>}
                </p>
              </div>
            )}
            {rotationResult && !rotationResult.error && rotationResult.updated === 0 && (
              <div style={{ background: 'rgba(251,146,60,0.05)', border: '1px solid rgba(251,146,60,0.3)', borderRadius: '10px', padding: '0.875rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                <p style={{ margin: 0, fontSize: '0.72rem', fontWeight: 700, color: '#fb923c' }}>⚠️ Ninguna parte actualizada</p>
                <p style={{ margin: 0, fontSize: '0.68rem', color: 'rgba(255,255,255,0.45)', lineHeight: 1.5 }}>
                  {rotationResult.skipped > 0
                    ? <>Saltadas: <strong style={{ color: '#fff' }}>{rotationResult.skipped}</strong>. Verificá que las columnas del Excel se llamen <strong style={{ color: '#fff' }}>part_code</strong> (o <strong style={{ color: '#fff' }}>codigo</strong>) y <strong style={{ color: '#fff' }}>rotation_class</strong> (o <strong style={{ color: '#fff' }}>rotacion</strong>), y que los códigos de parte coincidan exactamente con el catálogo.</>
                    : 'El archivo no tenía filas de datos para procesar.'}
                </p>
                {rotationResult.errors?.slice(0, 3).map((e, i) => (
                  <p key={i} style={{ margin: 0, fontSize: '0.63rem', color: 'rgba(255,255,255,0.3)', fontFamily: 'monospace' }}>
                    Fila {e.row}: {e.code || '—'} → {e.reason}
                  </p>
                ))}
              </div>
            )}
            {rotationResult?.error && (
              <p style={{ fontSize: '0.72rem', color: '#ef4444', margin: 0 }}>⚠️ {rotationResult.error}</p>
            )}

            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button
                onClick={handleRotationImport}
                disabled={!rotationFile || rotationUploading}
                style={{ flex: 1, background: 'rgba(99,102,241,0.15)', color: '#818cf8', border: '1px solid rgba(99,102,241,0.3)', borderRadius: '10px', padding: '0.7rem', fontWeight: 900, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.06em', cursor: (!rotationFile || rotationUploading) ? 'not-allowed' : 'pointer', opacity: (!rotationFile || rotationUploading) ? 0.4 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem' }}
              >
                <UploadCloud size={13} /> {rotationUploading ? 'Cargando...' : 'Cargar'}
              </button>
              <button
                onClick={() => setShowRotationUpload(false)}
                disabled={rotationUploading}
                style={{ flex: 1, background: 'rgba(255,255,255,0.03)', color: 'rgba(255,255,255,0.4)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '10px', padding: '0.7rem', fontWeight: 900, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.06em', cursor: 'pointer', opacity: rotationUploading ? 0.5 : 1 }}
              >
                Cerrar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal de confirmación de eliminación */}
      {deleteItem && (
        <div onClick={() => !deleteLoading && setDeleteItem(null)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(4px)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div onClick={e => e.stopPropagation()}
            style={{ background: '#0c0c0e', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '16px', padding: '2rem', width: '100%', maxWidth: '420px', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <Trash2 size={16} color="#ef4444" />
              <p style={{ color: '#fff', fontWeight: 900, fontSize: '0.82rem', textTransform: 'uppercase', letterSpacing: '0.05em', margin: 0 }}>Eliminar repuesto</p>
            </div>

            <div style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.15)', borderRadius: '10px', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              <span style={{ fontFamily: 'monospace', fontSize: '0.82rem', fontWeight: 700, color: '#ff5f33' }}>{deleteItem.factory_part_number}</span>
              <span style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.5)' }}>{deleteItem.description || '—'}</span>
            </div>

            <p style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.4)', margin: 0, lineHeight: 1.6 }}>
              Esta acción eliminará el repuesto del catálogo. Se borrarán también sus entradas en el manual de partes y las tareas de revisión de código asociadas.
            </p>

            {deleteError && (
              <p style={{ fontSize: '0.72rem', color: '#ef4444', margin: 0, fontWeight: 700 }}>⚠ {deleteError}</p>
            )}

            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button
                onClick={handleDeletePart}
                disabled={deleteLoading}
                style={{ flex: 1, background: 'rgba(239,68,68,0.15)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.35)', borderRadius: '10px', padding: '0.7rem', fontWeight: 900, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.06em', cursor: deleteLoading ? 'not-allowed' : 'pointer', opacity: deleteLoading ? 0.5 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem' }}
              >
                <Trash2 size={13} /> {deleteLoading ? 'Eliminando...' : 'Eliminar'}
              </button>
              <button
                onClick={() => setDeleteItem(null)}
                disabled={deleteLoading}
                style={{ flex: 1, background: 'rgba(255,255,255,0.03)', color: 'rgba(255,255,255,0.4)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '10px', padding: '0.7rem', fontWeight: 900, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.06em', cursor: 'pointer', opacity: deleteLoading ? 0.5 : 1 }}
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal de verificación de cambio de código */}
      {reviewTask && (
        <div onClick={() => !reviewLoading && setReviewTask(null)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div onClick={e => e.stopPropagation()}
            style={{ background: '#0c0c0e', border: '1px solid rgba(251,146,60,0.25)', borderRadius: '16px', padding: '2rem', width: '100%', maxWidth: '480px', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <AlertTriangle size={18} color="#fb923c" />
              <p style={{ color: '#fff', fontWeight: 900, fontSize: '0.82rem', textTransform: 'uppercase', letterSpacing: '0.05em', margin: 0 }}>Verificar cambio de código</p>
            </div>

            <p style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.45)', margin: 0, lineHeight: 1.6 }}>
              Un pedido reciente trae una descripción muy similar a esta parte pero con un código distinto. ¿Son la misma parte?
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: '10px', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                <p style={{ fontSize: '0.58rem', fontWeight: 800, color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: '0.08em', margin: 0 }}>Código actual (catálogo)</p>
                <p style={{ fontFamily: 'monospace', fontSize: '0.85rem', fontWeight: 700, color: '#ff5f33', margin: 0 }}>{reviewTask.existingCode}</p>
                <p style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.6)', margin: 0, lineHeight: 1.5 }}>{reviewTask.description}</p>
              </div>
              <div style={{ background: 'rgba(251,146,60,0.05)', borderRadius: '10px', padding: '1rem', border: '1px solid rgba(251,146,60,0.2)', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                <p style={{ fontSize: '0.58rem', fontWeight: 800, color: 'rgba(251,146,60,0.6)', textTransform: 'uppercase', letterSpacing: '0.08em', margin: 0 }}>Código candidato (pedido)</p>
                <p style={{ fontFamily: 'monospace', fontSize: '0.85rem', fontWeight: 700, color: '#fb923c', margin: 0 }}>{reviewTask.candidateCode}</p>
                <p style={{ fontSize: '0.62rem', color: 'rgba(255,255,255,0.35)', margin: 0 }}>
                  Similitud: <strong style={{ color: '#fb923c' }}>{reviewTask.score ? `${Math.round(reviewTask.score * 100)}%` : '—'}</strong>
                </p>
              </div>
            </div>

            {reviewMsg && (
              <p style={{ fontSize: '0.72rem', color: reviewMsg.startsWith('✅') ? '#4ade80' : '#ef4444', margin: 0, textAlign: 'center' }}>{reviewMsg}</p>
            )}

            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button
                onClick={() => handleReviewAction('approve')}
                disabled={reviewLoading}
                style={{ flex: 1, background: 'rgba(74,222,128,0.12)', color: '#4ade80', border: '1px solid rgba(74,222,128,0.25)', borderRadius: '10px', padding: '0.7rem', fontWeight: 900, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.06em', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem', opacity: reviewLoading ? 0.5 : 1 }}
              >
                <CheckCircle2 size={14} /> Sí, actualizar código
              </button>
              <button
                onClick={() => handleReviewAction('reject')}
                disabled={reviewLoading}
                style={{ flex: 1, background: 'rgba(239,68,68,0.08)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.2)', borderRadius: '10px', padding: '0.7rem', fontWeight: 900, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.06em', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem', opacity: reviewLoading ? 0.5 : 1 }}
              >
                <ShieldX size={14} /> No, descartar
              </button>
            </div>
          </div>
        </div>
      )}

      <style jsx>{`
        .master-table { width: 100%; border-collapse: collapse; }
        .master-table td { padding: 0.7rem 1rem; font-size: 0.68rem; }
        .sort-head { padding: 0.7rem 1rem; font-size: 0.58rem; font-weight: 800; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 0.1em; border-bottom: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.015); backdrop-filter: blur(10px); cursor: pointer; white-space: nowrap; text-align: left; user-select: none; position: sticky; top: 0; z-index: 10; }
        .sort-head:hover { color: #fff; background: rgba(255,255,255,0.03); }
        select option { background: #0c0c0e; color: #fff; }
      `}</style>
    </AdminLayout>
  );
}
