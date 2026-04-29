'use client';
import { useState, useEffect, useCallback } from 'react';
import AdminLayout from '../admin-layout';
import { authFetch } from '../../lib/authFetch';
import { Search, ChevronLeft, ChevronRight, X, ArrowUp, ArrowDown, ChevronsUpDown, AlertTriangle, CheckCircle2, ShieldX, Pencil } from 'lucide-react';

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

export default function PartsCatalogPage() {
  const [items, setItems]     = useState([]);
  const [total, setTotal]     = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage]       = useState(1);

  const [search, setSearch]           = useState('');
  const [searchInput, setSearchInput] = useState('');

  useEffect(() => {
    const t = setTimeout(() => { setSearch(searchInput); setPage(1); }, 350);
    return () => clearTimeout(t);
  }, [searchInput]);
  const [modelCode, setModelCode]     = useState('');
  const [models, setModels]           = useState([]);
  const [onlyPending, setOnlyPending] = useState(false);

  const [sortCol, setSortCol] = useState('section_code');
  const [sortDir, setSortDir] = useState('asc');

  // Modal de verificación
  const [reviewTask, setReviewTask] = useState(null); // { taskId, existingCode, candidateCode, score }
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewMsg, setReviewMsg] = useState('');

  // Modal de edición
  const [editItem, setEditItem] = useState(null);
  const [editForm, setEditForm] = useState({ description: '', description_es_manual: '', public_price: '' });
  const [editLoading, setEditLoading] = useState(false);
  const [editMsg, setEditMsg] = useState('');

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

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(PAGE_SIZE),
        search,
        model_code: modelCode,
        only_pending: String(onlyPending),
        sort_col: sortCol,
        sort_dir: sortDir,
      });
      const res = await authFetch(`/parts/admin/catalog?${params}`);
      if (res.ok) {
        const data = await res.json();
        setItems(data.items || []);
        setTotal(data.total || 0);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [page, search, modelCode, onlyPending, sortCol, sortDir]);

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

  const openEdit = (item) => {
    setEditMsg('');
    const defaultPrice = item.public_price != null
      ? String(item.public_price)
      : item.precio_publico_calculado != null
        ? String(Math.round(Number(item.precio_publico_calculado)))
        : '';
    setEditForm({
      description: item.description || '',
      description_es_manual: item.description_es || '',
      public_price: defaultPrice,
      new_code: '',
    });
    setEditItem(item);
  };

  const handleEditSave = async () => {
    if (!editItem) return;
    setEditLoading(true);
    setEditMsg('');
    const newCode = editForm.new_code.trim();
    try {
      if (newCode) {
        // Reemplazo de código — un solo endpoint que hace todo
        const body = { new_code: newCode };
        if (editForm.description.trim()) body.description = editForm.description.trim();
        body.description_es_manual = editForm.description_es_manual.trim() || null;
        const price = parseFloat(editForm.public_price);
        if (!isNaN(price) && price > 0) body.public_price = price;
        const res = await authFetch(`/parts/admin/catalog/${encodeURIComponent(editItem.factory_part_number)}/replace-code`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (res.ok) {
          setEditMsg('✅ Código reemplazado.');
          setTimeout(() => { setEditItem(null); fetchData(); }, 900);
        } else {
          const err = await res.json().catch(() => ({}));
          setEditMsg(`⚠️ ${err.detail || 'Error al reemplazar el código.'}`);
        }
      } else {
        // Solo actualización de campos — PATCH normal
        const body = {};
        if (editForm.description.trim()) body.description = editForm.description.trim();
        body.description_es_manual = editForm.description_es_manual.trim() || null;
        const price = parseFloat(editForm.public_price);
        if (!isNaN(price) && price > 0) body.public_price = price;
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
      }
    } catch { setEditMsg('⚠️ Error de conexión.'); }
    finally { setEditLoading(false); }
  };

  return (
    <AdminLayout>
      <header className="page-header">
        <div>
          <h1 className="page-title">Catálogo de <span style={{ fontStyle: 'italic', color: 'var(--accent-orange)', WebkitTextFillColor: 'var(--accent-orange)' }}>Partes</span></h1>
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
      </header>

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
              <th className="sort-head" onClick={() => toggleSort('avg_fob_cost')} style={{ whiteSpace: 'nowrap' }}>FOB Prom. <span style={{ fontWeight: 400, opacity: 0.5 }}>USD</span> <SortIcon col="avg_fob_cost" /></th>
              <th className="sort-head" onClick={() => toggleSort('avg_fob_cost')} style={{ whiteSpace: 'nowrap' }}>C. Importado <span style={{ fontWeight: 400, opacity: 0.5 }}>COP</span> <SortIcon col="avg_fob_cost" /></th>
              <th className="sort-head" onClick={() => toggleSort('avg_fob_cost')} style={{ whiteSpace: 'nowrap' }}>P. Distribuidor <span style={{ fontWeight: 400, opacity: 0.5 }}>COP</span> <SortIcon col="avg_fob_cost" /></th>
              <th className="sort-head" onClick={() => toggleSort('avg_fob_cost')} style={{ whiteSpace: 'nowrap' }}>P. Público Calc. <span style={{ fontWeight: 400, opacity: 0.5 }}>COP</span> <SortIcon col="avg_fob_cost" /></th>
              <th className="sort-head" onClick={() => toggleSort('public_price')} style={{ whiteSpace: 'nowrap' }}>Precio Final <SortIcon col="public_price" /></th>
              <th className="sort-head" style={{ width: '90px', textAlign: 'center' }}>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="10" style={{ textAlign: 'center', padding: '3rem', color: 'rgba(255,255,255,0.3)', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Cargando repuestos...</td></tr>
            ) : sortedItems.length === 0 ? (
              <tr><td colSpan="10" style={{ textAlign: 'center', padding: '4rem', color: 'rgba(255,255,255,0.2)', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                {!search && !modelCode && !onlyPending ? 'Sin repuestos cargados — subí los PDFs desde Configuración' : 'Sin resultados para la búsqueda'}
              </td></tr>
            ) : sortedItems.map((item, i) => (
              <tr key={`${item.factory_part_number}-${item.section_code}-${i}`} className="hover:bg-white/5 transition-colors border-b border-white/5">
                <td style={{ whiteSpace: 'nowrap' }}>
                  <span style={{ fontFamily: 'monospace', fontSize: '0.78rem', fontWeight: 700, color: '#ff5f33' }}>{item.factory_part_number}</span>
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
                <td><span style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.7)', fontWeight: 600 }}>{item.vehicle_model_name || '—'}</span></td>
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
                <td style={{ textAlign: 'center', whiteSpace: 'nowrap' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem' }}>
                    {item.pending_task_id && (
                      <button
                        onClick={() => openReview(item)}
                        title="Verificar posible cambio de código"
                        style={{ display: 'flex', alignItems: 'center', gap: '3px', fontSize: '0.6rem', fontWeight: 800, padding: '2px 8px', borderRadius: '20px', background: 'rgba(251,146,60,0.15)', color: '#fb923c', border: '1px solid rgba(251,146,60,0.35)', cursor: 'pointer', whiteSpace: 'nowrap', lineHeight: 1.4 }}
                      >
                        <AlertTriangle size={9} /> Verificar
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
            style={{ background: '#0c0c0e', border: '1px solid rgba(99,102,241,0.25)', borderRadius: '16px', padding: '2rem', width: '100%', maxWidth: '480px', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>

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
                <label style={{ display: 'block', fontSize: '0.62rem', fontWeight: 800, color: 'rgba(251,146,60,0.6)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.4rem' }}>
                  Nuevo código de fábrica <span style={{ fontWeight: 400, color: 'rgba(255,255,255,0.25)', textTransform: 'none', letterSpacing: 0 }}>— dejar vacío si no cambia</span>
                </label>
                <input
                  value={editForm.new_code}
                  onChange={e => setEditForm(f => ({ ...f, new_code: e.target.value }))}
                  placeholder={editItem?.factory_part_number}
                  style={{ width: '100%', padding: '0.6rem 0.85rem', background: editForm.new_code ? 'rgba(251,146,60,0.06)' : 'rgba(255,255,255,0.04)', border: `1px solid ${editForm.new_code ? 'rgba(251,146,60,0.35)' : 'rgba(255,255,255,0.1)'}`, borderRadius: '8px', color: editForm.new_code ? '#fb923c' : '#fff', fontSize: '0.78rem', fontFamily: 'monospace', outline: 'none', boxSizing: 'border-box', transition: 'all 0.2s' }}
                />
                {editForm.new_code && (
                  <p style={{ fontSize: '0.62rem', color: 'rgba(251,146,60,0.7)', margin: '0.35rem 0 0', lineHeight: 1.5 }}>
                    Se reemplazará <strong style={{ fontFamily: 'monospace' }}>{editItem?.factory_part_number}</strong> → <strong style={{ fontFamily: 'monospace' }}>{editForm.new_code.trim()}</strong> y se actualizará el historial de códigos.
                  </p>
                )}
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
