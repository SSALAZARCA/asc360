'use client';
import { useState, useEffect } from 'react';
import { authFetch } from '../../lib/authFetch';
import { ArrowUp, ArrowDown, ChevronsUpDown, RefreshCw, Download } from 'lucide-react';

const ROT = {
  baja:  { bg: 'rgba(74,222,128,0.12)',  color: '#4ade80',  border: 'rgba(74,222,128,0.3)',  label: 'BAJA'  },
  media: { bg: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: 'rgba(251,191,36,0.3)', label: 'MEDIA' },
};

// ciclo: sin marcar → cancelar → cambiar → sin marcar
const CYCLE = { '': 'cancelar', 'cancelar': 'cambiar', 'cambiar': '' };

const PI_STYLES = {
  '':         { bg: 'rgba(255,255,255,0.05)', border: 'rgba(255,255,255,0.1)',  piColor: 'rgba(255,255,255,0.7)', qtyColor: '#38bdf8',  prefix: null },
  'cancelar': { bg: 'rgba(239,68,68,0.12)',   border: 'rgba(239,68,68,0.35)',   piColor: '#fca5a5',               qtyColor: '#f87171',  prefix: '✕' },
  'cambiar':  { bg: 'rgba(251,191,36,0.1)',   border: 'rgba(251,191,36,0.35)',  piColor: '#fde68a',               qtyColor: '#fbbf24',  prefix: '↺' },
};

function RotBadge({ rc }) {
  const s = ROT[rc] || {};
  return (
    <span style={{
      fontSize: '0.58rem', fontWeight: 800, textTransform: 'uppercase',
      letterSpacing: '0.08em', padding: '2px 8px', borderRadius: '20px',
      background: s.bg, color: s.color, border: `1px solid ${s.border}`, whiteSpace: 'nowrap',
    }}>{s.label}</span>
  );
}

function SortIcon({ col, sortCol, sortDir }) {
  if (sortCol !== col) return <ChevronsUpDown size={10} style={{ opacity: 0.25, marginLeft: 3 }} />;
  return sortDir === 'asc'
    ? <ArrowUp   size={10} style={{ color: '#ff5f33', marginLeft: 3 }} />
    : <ArrowDown size={10} style={{ color: '#ff5f33', marginLeft: 3 }} />;
}

export default function AnalisisRepuestosTab() {
  const [data,      setData]      = useState(null);
  const [loading,   setLoading]   = useState(true);
  const [exporting, setExporting] = useState(false);
  const [rotFilter, setRotFilter] = useState('all');
  const [sortCol,   setSortCol]   = useState('rotation');
  const [sortDir,   setSortDir]   = useState('asc');

  // { lot_identifier: 'cancelar' | 'cambiar' }
  const [marked, setMarked] = useState({});

  const load = () => {
    setLoading(true);
    Promise.all([
      authFetch('/parts/admin/analysis/low-rotation-ordered').then(r => r.ok ? r.json() : null),
      authFetch('/parts/admin/analysis/decisions').then(r => r.ok ? r.json() : {}),
    ]).then(([analysisData, savedMarked]) => {
      if (analysisData) setData(analysisData);
      setMarked(savedMarked || {});
      setLoading(false);
    }).catch(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  // Clave compuesta para que la marcación sea independiente por referencia
  const markKey = (fpn, lotId) => `${fpn}::${lotId}`;

  const toggleMark = (fpn, lotId) => {
    const key  = markKey(fpn, lotId);
    setMarked(prev => {
      const next = CYCLE[prev[key] || ''];
      const copy = { ...prev };
      if (!next) delete copy[key]; else copy[key] = next;
      // Persistir en DB (fire-and-forget)
      authFetch('/parts/admin/analysis/decisions', {
        method: 'POST',
        body: JSON.stringify({ factory_part_number: fpn, lot_identifier: lotId, decision: next || '' }),
      }).catch(() => {});
      return copy;
    });
  };

  const toggleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir(col === 'rotation' ? 'asc' : 'desc'); }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await authFetch('/parts/admin/analysis/low-rotation-ordered/export', {
        method: 'POST',
        body: JSON.stringify({ marked }),
      });
      if (!res.ok) return;
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = `analisis_repuestos_${new Date().toISOString().slice(0, 10)}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  };

  const items = (data?.items || []).filter(i =>
    rotFilter === 'all' || i.rotation_class === rotFilter
  );

  const sorted = [...items].sort((a, b) => {
    let av, bv;
    if      (sortCol === 'rotation')  { av = a.rotation_class === 'baja' ? 0 : 1; bv = b.rotation_class === 'baja' ? 0 : 1; }
    else if (sortCol === 'total_qty') { av = a.total_qty;    bv = b.total_qty;    }
    else                              { av = a.lots.length;  bv = b.lots.length;  }
    return sortDir === 'asc' ? av - bv : bv - av;
  });

  // Para la barra de resumen: mostrar "CÓDIGO · PI"
  const markedCancelar = Object.entries(marked)
    .filter(([, v]) => v === 'cancelar')
    .map(([k]) => { const [fpn, pi] = k.split('::'); return { fpn, pi }; });
  const markedCambiar  = Object.entries(marked)
    .filter(([, v]) => v === 'cambiar')
    .map(([k]) => { const [fpn, pi] = k.split('::'); return { fpn, pi }; });
  const hasMarked = markedCancelar.length > 0 || markedCambiar.length > 0;

  const thStyle = {
    padding: '0.65rem 1rem', fontSize: '0.58rem', fontWeight: 800,
    color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', letterSpacing: '0.1em',
    borderBottom: '1px solid rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.015)',
    backdropFilter: 'blur(10px)', cursor: 'pointer', whiteSpace: 'nowrap',
    textAlign: 'left', userSelect: 'none', position: 'sticky', top: 0, zIndex: 10,
  };

  return (
    <div style={{ padding: '0 0 2rem' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 900, color: '#fff' }}>Para Revisar</h2>
          <p style={{ margin: '0.2rem 0 0', fontSize: '0.72rem', color: 'rgba(255,255,255,0.35)' }}>
            Baja/media rotación en pedido — click en un PI para marcarlo
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
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
          <button onClick={handleExport} disabled={exporting || !data} style={{
            display: 'flex', alignItems: 'center', gap: '0.35rem',
            padding: '0.5rem 0.9rem', borderRadius: '8px',
            background: 'rgba(74,222,128,0.1)', border: '1px solid rgba(74,222,128,0.25)',
            color: '#4ade80', fontSize: '0.68rem', fontWeight: 700,
            cursor: (exporting || !data) ? 'not-allowed' : 'pointer',
            opacity: (exporting || !data) ? 0.5 : 1,
          }}>
            <Download size={12} />
            {exporting ? 'Exportando...' : 'Exportar Excel'}
          </button>
        </div>
      </div>

      {/* Summary chips */}
      {data && (
        <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
          {[
            { label: 'Para revisar',    value: data.total_references, color: '#fff'    },
            { label: 'Unidades totales', value: data.total_qty,        color: '#38bdf8' },
            { label: 'Baja rotación',   value: data.baja_count,        color: '#4ade80' },
            { label: 'Media rotación',  value: data.media_count,       color: '#fbbf24' },
          ].map(({ label, value, color }) => (
            <div key={label} style={{
              background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: '10px', padding: '0.6rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.2rem',
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
              background:   active ? (color ? `${color}22` : 'rgba(255,255,255,0.08)') : 'rgba(255,255,255,0.03)',
              borderColor:  active ? (color ? `${color}66` : 'rgba(255,255,255,0.2)')  : 'rgba(255,255,255,0.08)',
              color:        active ? (color || '#fff') : 'rgba(255,255,255,0.4)',
            }}>{label}</button>
          );
        })}

        {/* Leyenda del ciclo */}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.62rem', color: 'rgba(255,255,255,0.3)' }}>
          <span>Click en un PI:</span>
          {[['cancelar','#f87171','rgba(239,68,68,0.12)'], ['cambiar','#fbbf24','rgba(251,191,36,0.1)']].map(([lbl, clr, bg]) => (
            <span key={lbl} style={{ padding: '1px 7px', borderRadius: '4px', background: bg, color: clr, fontWeight: 700, textTransform: 'uppercase', fontSize: '0.58rem' }}>{lbl}</span>
          ))}
        </div>
      </div>

      {/* Tabla */}
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
                <th style={thStyle}>Modelos</th>
                <th style={{ ...thStyle, textAlign: 'center' }} onClick={() => toggleSort('lots')}>
                  N° PIs <SortIcon col="lots" sortCol={sortCol} sortDir={sortDir} />
                </th>
                <th style={{ ...thStyle, textAlign: 'right' }} onClick={() => toggleSort('total_qty')}>
                  Total <SortIcon col="total_qty" sortCol={sortCol} sortDir={sortDir} />
                </th>
                <th style={{ ...thStyle, cursor: 'default' }}>PI numbers · cantidad <span style={{ fontWeight: 400, opacity: 0.5, textTransform: 'none', letterSpacing: 0 }}>— click para marcar</span></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((item, idx) => (
                <tr key={item.factory_part_number} style={{
                  borderBottom: '1px solid rgba(255,255,255,0.05)',
                  background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.012)',
                }}>
                  <td style={{ padding: '0.7rem 1rem' }}><RotBadge rc={item.rotation_class} /></td>
                  <td style={{ padding: '0.7rem 1rem' }}>
                    <span style={{ fontFamily: 'monospace', fontSize: '0.78rem', fontWeight: 700, color: '#ff5f33', whiteSpace: 'nowrap' }}>
                      {item.factory_part_number}
                    </span>
                  </td>
                  <td style={{ padding: '0.7rem 1rem', maxWidth: '280px' }}>
                    <span style={{
                      color: item.description_es ? '#4ade80' : 'rgba(255,255,255,0.6)',
                      fontSize: '0.72rem', display: 'block',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {item.description_es || item.description}
                    </span>
                  </td>
                  <td style={{ padding: '0.7rem 1rem' }}>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem' }}>
                      {(item.models || []).map(m => (
                        <span key={m} style={{
                          fontSize: '0.6rem', fontWeight: 700, padding: '2px 7px', borderRadius: '5px',
                          background: 'rgba(99,102,241,0.12)', border: '1px solid rgba(99,102,241,0.25)',
                          color: '#a5b4fc', whiteSpace: 'nowrap',
                        }}>{m}</span>
                      ))}
                    </div>
                  </td>
                  <td style={{ padding: '0.7rem 1rem', textAlign: 'center' }}>
                    <span style={{ fontSize: '0.78rem', fontWeight: 700, color: 'rgba(255,255,255,0.6)' }}>
                      {item.lots.length}
                    </span>
                  </td>
                  <td style={{ padding: '0.7rem 1rem', textAlign: 'right' }}>
                    <span style={{ fontFamily: 'monospace', fontWeight: 900, fontSize: '0.85rem', color: '#fff' }}>{item.total_qty}</span>
                    <span style={{ fontSize: '0.6rem', color: 'rgba(255,255,255,0.3)', marginLeft: '0.3rem' }}>u</span>
                  </td>
                  <td style={{ padding: '0.7rem 1rem' }}>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
                      {item.lots.map(lot => {
                        const state = marked[markKey(item.factory_part_number, lot.lot_identifier)] || '';
                        const s     = PI_STYLES[state];
                        return (
                          <button
                            key={lot.lot_identifier}
                            onClick={() => toggleMark(item.factory_part_number, lot.lot_identifier)}
                            title={state ? `Marcado: ${state} — click para cambiar` : 'Click para marcar'}
                            style={{
                              display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                              padding: '2px 8px', borderRadius: '6px', cursor: 'pointer',
                              background: s.bg, border: `1px solid ${s.border}`,
                              fontSize: '0.68rem', fontFamily: 'monospace', whiteSpace: 'nowrap',
                              transition: 'all 0.15s',
                            }}
                          >
                            {s.prefix && (
                              <span style={{ fontSize: '0.65rem', fontWeight: 900, color: s.piColor }}>{s.prefix}</span>
                            )}
                            <span style={{ color: s.piColor }}>{lot.lot_identifier}</span>
                            <span style={{ color: 'rgba(255,255,255,0.25)', fontSize: '0.6rem' }}>×</span>
                            <span style={{ color: s.qtyColor, fontWeight: 800 }}>{lot.qty}</span>
                          </button>
                        );
                      })}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Barra de decisiones marcadas */}
      {hasMarked && (
        <div style={{
          marginTop: '1rem', padding: '0.875rem 1.25rem',
          background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: '12px', display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-start',
        }}>
          {markedCancelar.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              <span style={{ fontSize: '0.58rem', fontWeight: 800, color: '#f87171', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                ✕ Cancelar ({markedCancelar.length})
              </span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem' }}>
                {markedCancelar.map(({ fpn, pi }) => (
                  <span key={`${fpn}::${pi}`} style={{
                    fontFamily: 'monospace', fontSize: '0.65rem', padding: '2px 8px', borderRadius: '5px',
                    background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.3)', color: '#fca5a5',
                    display: 'flex', gap: '0.3rem', alignItems: 'center',
                  }}>
                    <span style={{ color: 'rgba(255,255,255,0.35)', fontSize: '0.58rem' }}>{fpn}</span>
                    <span style={{ color: 'rgba(255,255,255,0.2)' }}>·</span>
                    <span>{pi}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
          {markedCambiar.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              <span style={{ fontSize: '0.58rem', fontWeight: 800, color: '#fbbf24', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                ↺ Cambiar ({markedCambiar.length})
              </span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem' }}>
                {markedCambiar.map(({ fpn, pi }) => (
                  <span key={`${fpn}::${pi}`} style={{
                    fontFamily: 'monospace', fontSize: '0.65rem', padding: '2px 8px', borderRadius: '5px',
                    background: 'rgba(251,191,36,0.1)', border: '1px solid rgba(251,191,36,0.3)', color: '#fde68a',
                    display: 'flex', gap: '0.3rem', alignItems: 'center',
                  }}>
                    <span style={{ color: 'rgba(255,255,255,0.35)', fontSize: '0.58rem' }}>{fpn}</span>
                    <span style={{ color: 'rgba(255,255,255,0.2)' }}>·</span>
                    <span>{pi}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
          <button
            onClick={() => {
              // Borrar todas las decisiones en DB
              Object.keys(marked).forEach(key => {
                const [fpn, lotId] = key.split('::');
                authFetch('/parts/admin/analysis/decisions', {
                  method: 'POST',
                  body: JSON.stringify({ factory_part_number: fpn, lot_identifier: lotId, decision: '' }),
                }).catch(() => {});
              });
              setMarked({});
            }}
            style={{
              marginLeft: 'auto', alignSelf: 'center', padding: '0.35rem 0.75rem', borderRadius: '7px',
              background: 'none', border: '1px solid rgba(255,255,255,0.1)', color: 'rgba(255,255,255,0.3)',
              fontSize: '0.62rem', fontWeight: 700, cursor: 'pointer',
            }}
          >
            Limpiar marcas
          </button>
        </div>
      )}

      <style jsx>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
