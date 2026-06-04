'use client';
import { useState, useEffect, useMemo } from 'react';
import { authFetch } from '../../lib/authFetch';
import { getApiUrl } from '../../lib/api';
import { RefreshCw } from 'lucide-react';

const BASE = () => `${getApiUrl()}/parts/admin/analysis/comparativa`;

const ROT_COLORS = {
  baja:  { color: '#f87171', bg: 'rgba(248,113,113,0.12)', border: 'rgba(248,113,113,0.3)' },
  media: { color: '#fbbf24', bg: 'rgba(251,191,36,0.12)',  border: 'rgba(251,191,36,0.3)'  },
};

export default function ComparativaTab() {
  const [items, setItems]       = useState([]);
  const [models, setModels]     = useState([]);
  const [loading, setLoading]   = useState(false);
  const [modelFilter, setModelFilter] = useState('');
  const [search, setSearch]     = useState('');

  const fetchData = async (mf = modelFilter) => {
    setLoading(true);
    try {
      const params = mf ? `?model_filter=${encodeURIComponent(mf)}` : '';
      const res = await authFetch(`${BASE()}${params}`);
      if (res.ok) {
        const data = await res.json();
        setItems(data.items || []);
        setModels(data.models || []);
      }
    } catch (e) {
      console.error('Error cargando comparativa:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.toLowerCase();
    return items.filter(i =>
      i.factory_part_number.toLowerCase().includes(q) ||
      (i.description_es || i.description || '').toLowerCase().includes(q)
    );
  }, [items, search]);

  const thStyle = {
    padding: '8px 12px', fontSize: '9px', fontWeight: 700, color: '#606075',
    textTransform: 'uppercase', letterSpacing: '0.07em',
    borderBottom: '1px solid rgba(255,255,255,0.06)',
    background: '#0e0e14', whiteSpace: 'nowrap', textAlign: 'right',
  };

  const fmt = (val) =>
    val != null
      ? `$${val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
        <div>
          <p style={{ margin: 0, fontSize: 14, fontWeight: 700, color: '#fff' }}>Comparativa de referencias</p>
          <p style={{ margin: '2px 0 0', fontSize: 11, color: '#606075' }}>
            Referencias compartidas entre modelos · costo FOB por modelo · {!loading && `${filtered.length} referencias`}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar referencia o descripción..."
            style={{
              padding: '6px 12px', borderRadius: 8, fontSize: 11,
              background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)',
              color: '#fff', outline: 'none', width: 240,
            }}
          />
          <select
            value={modelFilter}
            onChange={e => { setModelFilter(e.target.value); fetchData(e.target.value); }}
            style={{
              padding: '6px 12px', borderRadius: 8, fontSize: 11,
              background: '#1a1a24', border: '1px solid rgba(255,255,255,0.08)',
              color: '#fff', cursor: 'pointer',
            }}
          >
            <option value="">Todos los modelos</option>
            {models.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          <button
            onClick={() => fetchData()}
            style={{
              padding: '6px 10px', borderRadius: 8, border: 'none',
              background: 'rgba(255,255,255,0.06)', color: '#9ca3af', cursor: 'pointer',
            }}
          >
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      {/* Leyenda */}
      <div style={{ display: 'flex', gap: 16, fontSize: 10, color: '#606075' }}>
        <span>
          <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: 'rgba(251,191,36,0.35)', marginRight: 4 }} />
          Precio mínimo por referencia
        </span>
        <span>
          <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: 'rgba(34,197,94,0.2)', marginRight: 4 }} />
          Precio confirmado (packing list)
        </span>
        <span>
          <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: 'rgba(96,165,250,0.15)', marginRight: 4 }} />
          Precio estimado (FOB PI)
        </span>
      </div>

      {/* Tabla */}
      {loading ? (
        <div style={{ padding: 40, textAlign: 'center', color: '#606075', fontSize: 12 }}>Cargando...</div>
      ) : filtered.length === 0 ? (
        <div style={{ padding: 40, textAlign: 'center', color: '#606075', fontSize: 12 }}>
          Sin referencias compartidas entre modelos con historial de precios.
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, minWidth: 600 }}>
            <thead>
              <tr>
                <th style={{ ...thStyle, textAlign: 'left', position: 'sticky', left: 0, zIndex: 2 }}>Referencia</th>
                <th style={{ ...thStyle, textAlign: 'left', minWidth: 200 }}>Descripción</th>
                <th style={{ ...thStyle, textAlign: 'center' }}>Rot.</th>
                {models.map(m => (
                  <th key={m} style={{
                    ...thStyle,
                    color: modelFilter === m ? '#ff5f33' : '#606075',
                    borderBottom: modelFilter === m ? '2px solid rgba(255,95,51,0.5)' : '1px solid rgba(255,255,255,0.06)',
                  }}>
                    {m}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((item, idx) => {
                const costs = models.map(m => item.prices[m]?.fob_cost).filter(v => v != null);
                const minCost = costs.length ? Math.min(...costs) : null;

                return (
                  <tr key={item.factory_part_number} style={{
                    borderBottom: '1px solid rgba(255,255,255,0.04)',
                    background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.012)',
                  }}>
                    {/* Referencia */}
                    <td style={{
                      padding: '8px 12px', position: 'sticky', left: 0,
                      background: idx % 2 === 0 ? '#16161f' : '#17171f',
                    }}>
                      <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#ff5f33', fontSize: 11 }}>
                        {item.factory_part_number}
                      </span>
                    </td>

                    {/* Descripción */}
                    <td style={{ padding: '8px 12px', maxWidth: 240 }}>
                      <span style={{
                        color: item.description_es ? '#4ade80' : 'rgba(255,255,255,0.5)',
                        fontSize: 11, display: 'block',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {item.description_es || item.description}
                      </span>
                    </td>

                    {/* Rotación */}
                    <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                      {item.rotation_class ? (
                        <span style={{
                          fontSize: 9, fontWeight: 700, padding: '2px 6px', borderRadius: 4,
                          ...(ROT_COLORS[item.rotation_class] || { color: '#9ca3af', bg: 'transparent', border: 'transparent' }),
                          background: (ROT_COLORS[item.rotation_class] || {}).bg,
                          border: `1px solid ${(ROT_COLORS[item.rotation_class] || {}).border || 'transparent'}`,
                        }}>
                          {item.rotation_class.toUpperCase()}
                        </span>
                      ) : <span style={{ color: '#606075' }}>—</span>}
                    </td>

                    {/* Precio por modelo */}
                    {models.map(m => {
                      const entry = item.prices[m];
                      const isMin = entry != null && entry.fob_cost === minCost;
                      return (
                        <td key={m} style={{
                          padding: '8px 12px', textAlign: 'right', whiteSpace: 'nowrap',
                          background: isMin
                            ? 'rgba(251,191,36,0.18)'
                            : entry?.is_confirmed
                              ? 'rgba(34,197,94,0.06)'
                              : entry
                                ? 'rgba(96,165,250,0.06)'
                                : 'transparent',
                          borderLeft: '1px solid rgba(255,255,255,0.03)',
                        }}>
                          {entry ? (
                            <>
                              <span style={{
                                fontFamily: 'monospace', fontWeight: isMin ? 900 : 600,
                                fontSize: 11,
                                color: isMin ? '#fbbf24' : entry.is_confirmed ? '#4ade80' : '#93c5fd',
                              }}>
                                {fmt(entry.fob_cost)}
                              </span>
                              <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.25)', marginLeft: 3 }}>
                                {entry.is_confirmed ? 'PL' : 'PI'}
                              </span>
                            </>
                          ) : (
                            <span style={{ color: 'rgba(255,255,255,0.1)', fontSize: 10 }}>—</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
