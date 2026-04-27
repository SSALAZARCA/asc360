'use client';
import { useState, useEffect, useCallback, useMemo } from 'react';
import AdminLayout from '../admin-layout';
import { authFetch } from '../../lib/authFetch';
import { Search, ChevronLeft, ChevronRight, X, ArrowUpRight, ArrowDownRight, AlertTriangle, CheckCircle2, ShieldX } from 'lucide-react';

const PAGE_SIZE = 50;

export default function PartsCatalogPage() {
  const [items, setItems]     = useState([]);
  const [total, setTotal]     = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage]       = useState(1);

  const [search, setSearch]           = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [modelCode, setModelCode]     = useState('');
  const [models, setModels]           = useState([]);
  const [onlyPending, setOnlyPending] = useState(false);

  const [sortCol, setSortCol] = useState('section_code');
  const [sortDir, setSortDir] = useState('asc');

  // Modal de verificación
  const [reviewTask, setReviewTask] = useState(null); // { taskId, existingCode, candidateCode, score }
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewMsg, setReviewMsg] = useState('');

  useEffect(() => {
    authFetch('/parts/admin/vehicle-models')
      .then(r => r.ok ? r.json() : [])
      .then(data => setModels((Array.isArray(data) ? data : []).filter(m => m.catalog_model_code)))
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
  }, [page, search, modelCode, onlyPending]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const totalPages = Math.ceil(total / PAGE_SIZE);

  const handleSearch = (e) => { e.preventDefault(); setSearch(searchInput); setPage(1); };
  const clearSearch  = ()    => { setSearchInput(''); setSearch(''); setPage(1); };

  const toggleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir('asc'); }
  };
  const SortIcon = ({ col }) => sortCol === col
    ? (sortDir === 'asc' ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />)
    : null;

  const sortedItems = useMemo(() => {
    const arr = [...items];
    arr.sort((a, b) => {
      const va = a[sortCol] ?? '';
      const vb = b[sortCol] ?? '';
      const cmp = typeof va === 'number'
        ? va - vb
        : String(va).localeCompare(String(vb), 'es', { numeric: true });
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return arr;
  }, [items, sortCol, sortDir]);

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
        <form onSubmit={handleSearch} style={{ display: 'flex', gap: '0.5rem', flex: '1 1 280px', minWidth: 0 }}>
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
          <button type="submit" className="btn-primary" style={{ padding: '0.625rem 1.25rem', fontSize: '0.7rem' }}>Buscar</button>
        </form>

        <select
          value={modelCode}
          onChange={e => { setModelCode(e.target.value); setPage(1); }}
          style={{ padding: '0.625rem 1rem', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '10px', color: modelCode ? '#fff' : 'rgba(255,255,255,0.3)', fontSize: '0.78rem', outline: 'none', cursor: 'pointer', flexShrink: 0 }}
        >
          <option value="">Todos los modelos</option>
          {models.map(m => <option key={m.vehicle_model} value={m.catalog_model_code}>{m.vehicle_model}</option>)}
        </select>

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
                ['public_price',        'Precio Público'],
                ['section_code',        'Sección'],
                ['vehicle_model_name',  'Modelo'],
              ].map(([col, lbl]) => (
                <th key={col} onClick={() => toggleSort(col)} className="sort-head">
                  {lbl} <SortIcon col={col} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="6" style={{ textAlign: 'center', padding: '3rem', color: 'rgba(255,255,255,0.3)', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Cargando repuestos...</td></tr>
            ) : sortedItems.length === 0 ? (
              <tr><td colSpan="6" style={{ textAlign: 'center', padding: '4rem', color: 'rgba(255,255,255,0.2)', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                {!search && !modelCode && !onlyPending ? 'Sin repuestos cargados — subí los PDFs desde Configuración' : 'Sin resultados para la búsqueda'}
              </td></tr>
            ) : sortedItems.map((item, i) => (
              <tr key={`${item.factory_part_number}-${item.section_code}-${i}`} className="hover:bg-white/5 transition-colors border-b border-white/5">
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ fontFamily: 'monospace', fontSize: '0.78rem', fontWeight: 700, color: '#ff5f33' }}>{item.factory_part_number}</span>
                    {item.pending_task_id && (
                      <button
                        onClick={() => openReview(item)}
                        title="Verificar posible cambio de código"
                        style={{ display: 'flex', alignItems: 'center', gap: '3px', fontSize: '0.6rem', fontWeight: 800, padding: '2px 8px', borderRadius: '20px', background: 'rgba(251,146,60,0.15)', color: '#fb923c', border: '1px solid rgba(251,146,60,0.35)', cursor: 'pointer', whiteSpace: 'nowrap', lineHeight: 1.4 }}
                      >
                        <AlertTriangle size={9} /> Verificar
                      </button>
                    )}
                  </div>
                </td>
                <td style={{ color: 'rgba(255,255,255,0.85)', maxWidth: '280px' }}>
                  <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.description || '—'}</span>
                </td>
                <td style={{ maxWidth: '240px' }}>
                  {item.description_es
                    ? <span style={{ color: '#4ade80', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.description_es}</span>
                    : <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: '0.68rem' }}>—</span>
                  }
                </td>
                <td>
                  {item.public_price != null
                    ? <span style={{ fontWeight: 700, color: '#10b981' }}>${Number(item.public_price).toLocaleString('es-CO')}</span>
                    : <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: '0.68rem' }}>—</span>
                  }
                </td>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ fontSize: '0.6rem', fontWeight: 800, padding: '2px 8px', borderRadius: '20px', background: 'rgba(99,102,241,0.12)', color: '#818cf8', border: '1px solid rgba(99,102,241,0.2)', whiteSpace: 'nowrap' }}>{item.section_code}</span>
                    <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '140px' }}>{item.section_name}</span>
                  </div>
                </td>
                <td><span style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.7)', fontWeight: 600 }}>{item.vehicle_model_name || '—'}</span></td>
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
        .master-table td { padding: 0.875rem 1.5rem; }
        .sort-head { padding: 0.7rem 1.5rem; font-size: 0.62rem; font-weight: 800; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 0.08em; border-bottom: 1px solid rgba(255,255,255,0.05); background: rgba(0,0,0,0.2); cursor: pointer; white-space: nowrap; text-align: left; user-select: none; }
        .sort-head:hover { color: #fff; }
        select option { background: #0c0c0e; color: #fff; }
      `}</style>
    </AdminLayout>
  );
}
