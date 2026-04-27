'use client';
import { useState, useEffect, useCallback } from 'react';
import AdminLayout from '../admin-layout';
import { authFetch } from '../../lib/authFetch';
import { BookOpen, Search, ChevronLeft, ChevronRight, X } from 'lucide-react';

const PAGE_SIZE = 50;

export default function PartsCatalogPage() {
  const [items, setItems]         = useState([]);
  const [total, setTotal]         = useState(0);
  const [loading, setLoading]     = useState(false);
  const [page, setPage]           = useState(1);

  const [search, setSearch]       = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [modelCode, setModelCode] = useState('');

  const [models, setModels]       = useState([]);

  useEffect(() => {
    authFetch('/parts/admin/vehicle-models')
      .then(r => r.ok ? r.json() : [])
      .then(data => {
        const withCatalog = (Array.isArray(data) ? data : []).filter(m => m.catalog_model_code);
        setModels(withCatalog);
      })
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
      <div style={{ maxWidth: '1100px', margin: '0 auto', padding: '2rem 1.5rem' }}>

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
              {total > 0 ? `${total.toLocaleString()} repuestos cargados` : 'Consulta el catálogo de despiece'}
            </p>
          </div>
        </div>

        {/* Filtros */}
        <div className="glass" style={{ borderRadius: '14px', padding: '1.25rem', marginBottom: '1.5rem', display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          {/* Búsqueda */}
          <form onSubmit={handleSearch} style={{ display: 'flex', gap: '0.5rem', flex: '1 1 280px' }}>
            <div style={{ flex: 1, position: 'relative' }}>
              <Search size={14} color="#606075" style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
              <input
                value={searchInput}
                onChange={e => setSearchInput(e.target.value)}
                placeholder="Buscar por código, descripción..."
                style={{ width: '100%', padding: '0.6rem 2.2rem 0.6rem 2.2rem', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', color: '#fff', fontSize: '0.78rem', outline: 'none', boxSizing: 'border-box' }}
              />
              {searchInput && (
                <button type="button" onClick={clearSearch} style={{ position: 'absolute', right: '0.6rem', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: '#606075', cursor: 'pointer', display: 'flex' }}>
                  <X size={13} />
                </button>
              )}
            </div>
            <button type="submit" style={{ padding: '0.6rem 1.1rem', borderRadius: '8px', border: 'none', background: '#ff5f33', color: '#fff', fontWeight: 700, fontSize: '0.7rem', cursor: 'pointer', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Buscar
            </button>
          </form>

          {/* Filtro modelo */}
          <div style={{ flex: '0 1 220px' }}>
            <select
              value={modelCode}
              onChange={e => { setModelCode(e.target.value); setPage(1); }}
              style={{ width: '100%', padding: '0.6rem 0.875rem', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', color: modelCode ? '#fff' : '#606075', fontSize: '0.78rem', outline: 'none', appearance: 'none', cursor: 'pointer' }}
            >
              <option value="">Todos los modelos</option>
              {models.map(m => (
                <option key={m.vehicle_model} value={m.catalog_model_code}>{m.vehicle_model}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Tabla */}
        <div className="glass" style={{ borderRadius: '14px', overflow: 'hidden' }}>
          {loading ? (
            <div style={{ padding: '3rem', textAlign: 'center', color: '#606075', fontSize: '0.78rem' }}>
              Cargando repuestos...
            </div>
          ) : items.length === 0 ? (
            <div style={{ padding: '3rem', textAlign: 'center', color: '#606075' }}>
              <BookOpen size={32} style={{ margin: '0 auto 0.75rem', display: 'block', opacity: 0.2 }} />
              <p style={{ margin: 0, fontSize: '0.8rem' }}>
                {total === 0 && !search && !modelCode
                  ? 'No hay repuestos cargados aún. Subí los PDFs desde Configuración.'
                  : 'No se encontraron resultados para la búsqueda.'}
              </p>
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                <thead>
                  <tr style={{ background: 'rgba(0,0,0,0.3)' }}>
                    {['#', 'Ref. Fábrica', 'Ref. UM', 'Descripción', 'Unidad', 'Sección', 'Modelo'].map(h => (
                      <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontSize: '9px', fontWeight: 700, color: '#606075', textTransform: 'uppercase', letterSpacing: '0.07em', borderBottom: '1px solid rgba(255,255,255,0.06)', whiteSpace: 'nowrap' }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {items.map((item, i) => (
                    <tr key={`${item.factory_part_number}-${item.section_code}-${i}`} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}
                      onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    >
                      <td style={{ padding: '9px 14px', color: '#606075', fontWeight: 600 }}>{item.order_num}</td>
                      <td style={{ padding: '9px 14px', color: '#ff5f33', fontWeight: 700, fontFamily: 'monospace', whiteSpace: 'nowrap' }}>{item.factory_part_number}</td>
                      <td style={{ padding: '9px 14px', color: '#60a5fa', fontWeight: 600, fontFamily: 'monospace', whiteSpace: 'nowrap' }}>{item.um_part_number || '—'}</td>
                      <td style={{ padding: '9px 14px', color: '#e2e8f0', maxWidth: '260px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.description || '—'}</td>
                      <td style={{ padding: '9px 14px', color: '#9ca3af', whiteSpace: 'nowrap' }}>{item.unit || '—'}</td>
                      <td style={{ padding: '9px 14px', whiteSpace: 'nowrap' }}>
                        <span style={{ fontSize: '9px', fontWeight: 700, padding: '2px 8px', borderRadius: '20px', background: 'rgba(99,102,241,0.1)', color: '#818cf8', border: '1px solid rgba(99,102,241,0.2)' }}>
                          {item.section_code}
                        </span>
                        <span style={{ marginLeft: '6px', color: '#606075' }}>{item.section_name}</span>
                      </td>
                      <td style={{ padding: '9px 14px', color: '#606075', whiteSpace: 'nowrap', fontFamily: 'monospace', fontSize: '10px' }}>{item.model_code}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Paginación */}
          {totalPages > 1 && (
            <div style={{ padding: '1rem 1.25rem', borderTop: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '0.68rem', color: '#606075', fontWeight: 600 }}>
                Página {page} de {totalPages} · {total.toLocaleString()} resultados
              </span>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  style={{ padding: '0.4rem 0.75rem', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.04)', color: page === 1 ? '#404055' : '#fff', cursor: page === 1 ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.7rem', fontWeight: 700 }}
                >
                  <ChevronLeft size={13} /> Anterior
                </button>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  style={{ padding: '0.4rem 0.75rem', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.04)', color: page === totalPages ? '#404055' : '#fff', cursor: page === totalPages ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.7rem', fontWeight: 700 }}
                >
                  Siguiente <ChevronRight size={13} />
                </button>
              </div>
            </div>
          )}
        </div>

      </div>

      <style jsx global>{`
        select option { background: #0c0c0e; color: #fff; }
      `}</style>
    </AdminLayout>
  );
}
