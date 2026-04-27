'use client';
import { useState, useEffect, useCallback } from 'react';
import AdminLayout from '../admin-layout';
import { authFetch } from '../../lib/authFetch';
import { Search, ChevronLeft, ChevronRight, X } from 'lucide-react';

const PAGE_SIZE = 50;

export default function PartsCatalogPage() {
  const [items, setItems]     = useState([]);
  const [total, setTotal]     = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage]       = useState(1);

  const [search, setSearch]         = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [modelCode, setModelCode]   = useState('');
  const [models, setModels]         = useState([]);

  useEffect(() => {
    authFetch('/parts/admin/vehicle-models')
      .then(r => r.ok ? r.json() : [])
      .then(data => setModels((Array.isArray(data) ? data : []).filter(m => m.catalog_model_code)))
      .catch(() => {});
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE), search, model_code: modelCode });
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
  }, [page, search, modelCode]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const totalPages = Math.ceil(total / PAGE_SIZE);

  const handleSearch = (e) => {
    e.preventDefault();
    setSearch(searchInput);
    setPage(1);
  };

  const clearSearch = () => {
    setSearchInput('');
    setSearch('');
    setPage(1);
  };

  return (
    <AdminLayout>
      <header className="page-header">
        <div>
          <h1 className="page-title">Catálogo de <span style={{ fontStyle: 'italic', color: 'var(--accent-orange)', WebkitTextFillColor: 'var(--accent-orange)' }}>Partes</span></h1>
          <p className="page-subtitle">
            {total > 0 ? `${total.toLocaleString()} repuestos cargados en el sistema` : 'Consulta el catálogo de despiece de todos los modelos'}
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
          <button type="submit" className="btn-primary" style={{ padding: '0.625rem 1.25rem', fontSize: '0.7rem' }}>
            Buscar
          </button>
        </form>

        <select
          value={modelCode}
          onChange={e => { setModelCode(e.target.value); setPage(1); }}
          style={{ padding: '0.625rem 1rem', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '10px', color: modelCode ? '#fff' : 'rgba(255,255,255,0.3)', fontSize: '0.78rem', outline: 'none', cursor: 'pointer', flexShrink: 0 }}
        >
          <option value="">Todos los modelos</option>
          {models.map(m => (
            <option key={m.vehicle_model} value={m.catalog_model_code}>{m.vehicle_model}</option>
          ))}
        </select>
      </div>

      {/* Tabla */}
      <div className="glass table-scroll-wrapper rounded-2xl border border-white/5 shadow-2xl">
        <table className="master-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Ref. Fábrica</th>
              <th>Descripción</th>
              <th>Sección</th>
              <th>Modelo</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan="5" style={{ textAlign: 'center', padding: '3rem', color: 'rgba(255,255,255,0.3)', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  Cargando repuestos...
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan="5" style={{ textAlign: 'center', padding: '4rem', color: 'rgba(255,255,255,0.2)', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  {!search && !modelCode ? 'Sin repuestos cargados — subí los PDFs desde Configuración' : 'Sin resultados para la búsqueda'}
                </td>
              </tr>
            ) : items.map((item, i) => (
              <tr key={`${item.factory_part_number}-${item.section_code}-${i}`} className="hover:bg-white/5 transition-colors border-b border-white/5">
                <td style={{ color: 'rgba(255,255,255,0.35)', fontWeight: 700 }}>{item.order_num}</td>
                <td><span style={{ fontFamily: 'monospace', fontSize: '0.78rem', fontWeight: 700, color: '#ff5f33' }}>{item.factory_part_number}</span></td>
                <td style={{ color: 'rgba(255,255,255,0.85)', maxWidth: '380px' }}>
                  <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.description || '—'}</span>
                </td>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ fontSize: '0.6rem', fontWeight: 800, padding: '2px 8px', borderRadius: '20px', background: 'rgba(99,102,241,0.12)', color: '#818cf8', border: '1px solid rgba(99,102,241,0.2)', whiteSpace: 'nowrap' }}>
                      {item.section_code}
                    </span>
                    <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '160px' }}>{item.section_name}</span>
                  </div>
                </td>
                <td><span style={{ fontFamily: 'monospace', fontSize: '0.68rem', color: 'rgba(255,255,255,0.3)', fontWeight: 600 }}>{item.model_code}</span></td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Paginación */}
        {totalPages > 1 && (
          <div style={{ padding: '1rem 1.5rem', borderTop: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.3)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Página {page} de {totalPages} · {total.toLocaleString()} resultados
            </span>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="btn" style={{ padding: '0.4rem 0.875rem', fontSize: '0.68rem', display: 'flex', alignItems: 'center', gap: '0.3rem', opacity: page === 1 ? 0.4 : 1 }}>
                <ChevronLeft size={13} /> Anterior
              </button>
              <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages} className="btn" style={{ padding: '0.4rem 0.875rem', fontSize: '0.68rem', display: 'flex', alignItems: 'center', gap: '0.3rem', opacity: page === totalPages ? 0.4 : 1 }}>
                Siguiente <ChevronRight size={13} />
              </button>
            </div>
          </div>
        )}
      </div>

      <style jsx>{`
        .master-table { width: 100%; border-collapse: collapse; }
        .master-table th { text-align: left; padding: 1.25rem 1.5rem; color: rgba(255,255,255,0.4); font-weight: 800; border-bottom: 1px solid rgba(255,255,255,0.05); text-transform: uppercase; font-size: 0.65rem; letter-spacing: 0.05em; background: rgba(0,0,0,0.2); }
        .master-table td { padding: 0.875rem 1.5rem; }
        select option { background: #0c0c0e; color: #fff; }
      `}</style>
    </AdminLayout>
  );
}
