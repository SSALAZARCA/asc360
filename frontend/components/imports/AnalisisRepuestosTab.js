'use client';
import { useState, useEffect } from 'react';
import { authFetch } from '../../lib/authFetch';
import { ArrowUp, ArrowDown, ChevronsUpDown, RefreshCw } from 'lucide-react';

const ROT = {
  baja:  { bg: 'rgba(74,222,128,0.12)',  color: '#4ade80',  border: 'rgba(74,222,128,0.3)',  label: 'BAJA'  },
  media: { bg: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: 'rgba(251,191,36,0.3)', label: 'MEDIA' },
};

function RotBadge({ rc }) {
  const s = ROT[rc] || {};
  return (
    <span style={{
      fontSize: '0.58rem', fontWeight: 800, textTransform: 'uppercase',
      letterSpacing: '0.08em', padding: '2px 8px', borderRadius: '20px',
      background: s.bg, color: s.color, border: `1px solid ${s.border}`,
      whiteSpace: 'nowrap',
    }}>
      {s.label}
    </span>
  );
}

function SortIcon({ col, sortCol, sortDir }) {
  if (sortCol !== col) return <ChevronsUpDown size={10} style={{ opacity: 0.25, marginLeft: 3 }} />;
  return sortDir === 'asc'
    ? <ArrowUp size={10} style={{ color: '#ff5f33', marginLeft: 3 }} />
    : <ArrowDown size={10} style={{ color: '#ff5f33', marginLeft: 3 }} />;
}

export default function AnalisisRepuestosTab() {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [rotFilter, setRotFilter] = useState('all');
  const [sortCol, setSortCol]     = useState('rotation');
  const [sortDir, setSortDir]     = useState('asc');

  const load = () => {
    setLoading(true);
    authFetch('/parts/admin/analysis/low-rotation-ordered')
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const toggleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir(col === 'rotation' ? 'asc' : 'desc'); }
  };

  const items = (data?.items || []).filter(i =>
    rotFilter === 'all' || i.rotation_class === rotFilter
  );

  const sorted = [...items].sort((a, b) => {
    let av, bv;
    if (sortCol === 'rotation') {
      av = a.rotation_class === 'baja' ? 0 : 1;
      bv = b.rotation_class === 'baja' ? 0 : 1;
    } else if (sortCol === 'total_qty') {
      av = a.total_qty; bv = b.total_qty;
    } else {
      av = a.lots.length; bv = b.lots.length;
    }
    return sortDir === 'asc' ? av - bv : bv - av;
  });

  const thStyle = {
    padding: '0.65rem 1rem', fontSize: '0.58rem', fontWeight: 800,
    color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase',
    letterSpacing: '0.1em', borderBottom: '1px solid rgba(255,255,255,0.08)',
    background: 'rgba(255,255,255,0.015)', backdropFilter: 'blur(10px)',
    cursor: 'pointer', whiteSpace: 'nowrap', textAlign: 'left',
    userSelect: 'none', position: 'sticky', top: 0, zIndex: 10,
  };

  return (
    <div style={{ padding: '0 0 2rem' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 900, color: '#fff' }}>
            Para Revisar
          </h2>
          <p style={{ margin: '0.2rem 0 0', fontSize: '0.72rem', color: 'rgba(255,255,255,0.35)' }}>
            Repuestos baja/media rotación en pedido — aún cancelables
          </p>
        </div>
        <button onClick={load} disabled={loading} style={{
          display: 'flex', alignItems: 'center', gap: '0.35rem',
          padding: '0.5rem 0.9rem', borderRadius: '8px',
          background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
          color: 'rgba(255,255,255,0.4)', fontSize: '0.68rem', fontWeight: 700,
          cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.5 : 1,
        }}>
          <RefreshCw size={12} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
          Actualizar
        </button>
      </div>

      {/* Summary chips */}
      {data && (
        <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
          {[
            { label: 'Para revisar',    value: data.total_references, color: '#fff' },
            { label: 'Unidades totales', value: data.total_qty,        color: '#38bdf8' },
            { label: 'Baja rotación',   value: data.baja_count,        color: '#4ade80' },
            { label: 'Media rotación',  value: data.media_count,       color: '#fbbf24' },
          ].map(({ label, value, color }) => (
            <div key={label} style={{
              background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: '10px', padding: '0.6rem 1rem',
              display: 'flex', flexDirection: 'column', gap: '0.2rem',
            }}>
              <span style={{ fontSize: '0.58rem', fontWeight: 700, color: 'rgba(255,255,255,0.35)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{label}</span>
              <span style={{ fontSize: '1.2rem', fontWeight: 900, color, fontFamily: 'monospace' }}>{value.toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}

      {/* Filter toggle */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        {[
          { val: 'all',   label: 'Todas' },
          { val: 'baja',  label: 'Baja',  color: '#4ade80' },
          { val: 'media', label: 'Media', color: '#fbbf24' },
        ].map(({ val, label, color }) => {
          const active = rotFilter === val;
          return (
            <button key={val} onClick={() => setRotFilter(val)} style={{
              padding: '0.4rem 0.85rem', borderRadius: '8px', fontSize: '0.7rem',
              fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em',
              cursor: 'pointer', border: '1px solid', transition: 'all 0.15s',
              background: active ? (color ? `${color}22` : 'rgba(255,255,255,0.08)') : 'rgba(255,255,255,0.03)',
              borderColor: active ? (color ? `${color}66` : 'rgba(255,255,255,0.2)') : 'rgba(255,255,255,0.08)',
              color: active ? (color || '#fff') : 'rgba(255,255,255,0.4)',
            }}>{label}</button>
          );
        })}
      </div>

      {/* Table */}
      <div className="glass table-scroll-wrapper rounded-2xl border border-white/5 shadow-2xl">
        {loading ? (
          <div style={{ padding: '4rem', textAlign: 'center', color: 'rgba(255,255,255,0.25)', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
            Cargando análisis...
          </div>
        ) : sorted.length === 0 ? (
          <div style={{ padding: '4rem', textAlign: 'center', color: 'rgba(255,255,255,0.2)', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
            {data ? 'Sin repuestos para revisar en este filtro' : 'Error al cargar datos'}
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={thStyle} onClick={() => toggleSort('rotation')}>
                  Rotación <SortIcon col="rotation" sortCol={sortCol} sortDir={sortDir} />
                </th>
                <th style={thStyle}>Código</th>
                <th style={thStyle}>Descripción</th>
                <th style={{ ...thStyle, textAlign: 'center' }} onClick={() => toggleSort('lots')}>
                  N° PIs <SortIcon col="lots" sortCol={sortCol} sortDir={sortDir} />
                </th>
                <th style={{ ...thStyle, textAlign: 'right' }} onClick={() => toggleSort('total_qty')}>
                  Total <SortIcon col="total_qty" sortCol={sortCol} sortDir={sortDir} />
                </th>
                <th style={thStyle}>PI numbers · cantidad</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((item, idx) => (
                <tr key={item.factory_part_number} style={{
                  borderBottom: '1px solid rgba(255,255,255,0.05)',
                  background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.012)',
                }}>
                  <td style={{ padding: '0.7rem 1rem' }}>
                    <RotBadge rc={item.rotation_class} />
                  </td>
                  <td style={{ padding: '0.7rem 1rem' }}>
                    <span style={{ fontFamily: 'monospace', fontSize: '0.78rem', fontWeight: 700, color: '#ff5f33', whiteSpace: 'nowrap' }}>
                      {item.factory_part_number}
                    </span>
                  </td>
                  <td style={{ padding: '0.7rem 1rem', maxWidth: '280px' }}>
                    {item.description_es ? (
                      <span style={{ color: '#4ade80', fontSize: '0.72rem', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {item.description_es}
                      </span>
                    ) : (
                      <span style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.72rem', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {item.description}
                      </span>
                    )}
                  </td>
                  <td style={{ padding: '0.7rem 1rem', textAlign: 'center' }}>
                    <span style={{ fontSize: '0.78rem', fontWeight: 700, color: 'rgba(255,255,255,0.6)' }}>
                      {item.lots.length}
                    </span>
                  </td>
                  <td style={{ padding: '0.7rem 1rem', textAlign: 'right' }}>
                    <span style={{ fontFamily: 'monospace', fontWeight: 900, fontSize: '0.85rem', color: '#fff' }}>
                      {item.total_qty}
                    </span>
                    <span style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.3)', marginLeft: '0.3rem' }}>u</span>
                  </td>
                  <td style={{ padding: '0.7rem 1rem' }}>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
                      {item.lots.map(lot => (
                        <span key={lot.lot_identifier} style={{
                          display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                          padding: '2px 8px', borderRadius: '6px',
                          background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                          fontSize: '0.68rem', fontFamily: 'monospace', whiteSpace: 'nowrap',
                        }}>
                          <span style={{ color: 'rgba(255,255,255,0.7)' }}>{lot.lot_identifier}</span>
                          <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: '0.6rem' }}>×</span>
                          <span style={{ color: '#38bdf8', fontWeight: 800 }}>{lot.qty}</span>
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <style jsx>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
