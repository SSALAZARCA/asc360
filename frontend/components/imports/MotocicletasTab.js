'use client';
import { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../../lib/authFetch';
import { getApiUrl } from '../../lib/api';
import { FileUp, Download, RefreshCw, Search, CheckCircle, Clock, Bike, X, AlertCircle, Pencil, Send, FileText, Trash2, MapPin, AlertTriangle, FileSpreadsheet, Receipt, ShieldCheck, Lock } from 'lucide-react';
import { toast } from '../../lib/toast';
import ConfirmModal from '../ConfirmModal';

// ---------------------------------------------------------------------------
// Error modal estilizado
// ---------------------------------------------------------------------------
function ErrorModal({ message, onClose }) {
  if (!message) return null;
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: '#16161f', border: '1px solid rgba(248,113,113,0.3)',
        borderRadius: '14px', padding: '24px', width: 400, maxWidth: '90vw',
        display: 'flex', flexDirection: 'column', gap: '14px',
        boxShadow: '0 16px 48px rgba(0,0,0,0.6)',
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
          <div style={{ padding: '6px', borderRadius: '8px', background: 'rgba(248,113,113,0.1)', flexShrink: 0 }}>
            <AlertTriangle size={16} color="#f87171" />
          </div>
          <div style={{ flex: 1 }}>
            <p style={{ margin: '0 0 4px', fontSize: '12px', fontWeight: 700, color: '#f87171' }}>
              No se puede generar el empadronamiento
            </p>
            <p style={{ margin: 0, fontSize: '11px', color: '#9ca3af', lineHeight: 1.6 }}>
              {message}
            </p>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#606075', cursor: 'pointer', padding: 0, flexShrink: 0 }}>
            <X size={14} />
          </button>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            style={{
              padding: '7px 20px', borderRadius: '8px',
              border: '1px solid rgba(248,113,113,0.3)',
              background: 'rgba(248,113,113,0.08)',
              color: '#f87171', fontSize: '11px', fontWeight: 700, cursor: 'pointer',
            }}
          >
            Entendido
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Modal de confirmación de eliminación
// ---------------------------------------------------------------------------
function ConfirmDeleteModal({ unit, onConfirm, onClose }) {
  if (!unit) return null;
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(0,0,0,0.72)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: '#16161f', border: '1px solid rgba(248,113,113,0.25)',
        borderRadius: '14px', padding: '24px', width: 400, maxWidth: '90vw',
        display: 'flex', flexDirection: 'column', gap: '16px',
        boxShadow: '0 16px 48px rgba(0,0,0,0.6)',
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
          <div style={{ padding: '6px', borderRadius: '8px', background: 'rgba(248,113,113,0.1)', flexShrink: 0 }}>
            <Trash2 size={16} color="#f87171" />
          </div>
          <div style={{ flex: 1 }}>
            <p style={{ margin: '0 0 6px', fontSize: '13px', fontWeight: 700, color: '#fff' }}>
              Eliminar unidad
            </p>
            <p style={{ margin: 0, fontSize: '11px', color: '#9ca3af', lineHeight: 1.6 }}>
              ¿Confirmás la eliminación de{' '}
              <span style={{ color: '#e2e8f0', fontWeight: 600 }}>
                {unit.vin_number || unit.id}
              </span>
              ?<br />Esta acción no se puede deshacer.
            </p>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#606075', cursor: 'pointer', padding: 0, flexShrink: 0 }}>
            <X size={14} />
          </button>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
          <button
            onClick={onClose}
            style={{
              padding: '7px 16px', borderRadius: '8px',
              border: '1px solid rgba(255,255,255,0.08)',
              background: 'transparent', color: '#9ca3af',
              fontSize: '11px', fontWeight: 600, cursor: 'pointer',
            }}
          >
            Cancelar
          </button>
          <button
            onClick={onConfirm}
            style={{
              padding: '7px 18px', borderRadius: '8px', border: 'none',
              background: '#f87171', color: '#0d0d14',
              fontSize: '11px', fontWeight: 700, cursor: 'pointer',
            }}
          >
            Eliminar
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Badge de empadronamiento
// ---------------------------------------------------------------------------
function CertBadge({ generated }) {
  if (generated) {
    return (
      <span title="Empadronado" style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 24, height: 24, borderRadius: '50%',
        background: 'rgba(34,197,94,0.1)', color: '#22c55e',
        border: '1px solid rgba(34,197,94,0.25)',
      }}>
        <CheckCircle size={13} />
      </span>
    );
  }
  return (
    <span title="Pendiente de empadronamiento" style={{
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      width: 24, height: 24, borderRadius: '50%',
      background: 'rgba(96,96,117,0.1)', color: '#404050',
      border: '1px solid rgba(96,96,117,0.2)',
    }}>
      <Clock size={13} />
    </span>
  );
}

// ---------------------------------------------------------------------------
// Modal inline para carga de DIM
// ---------------------------------------------------------------------------
function DimUploadModal({ onUpload, onClose, uploading, result }) {
  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    onUpload(file);
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: '#13131a', border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '16px', padding: '28px', width: '460px', maxWidth: '92vw',
        display: 'flex', flexDirection: 'column', gap: '20px',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ color: '#fff', fontWeight: 700, fontSize: '15px', margin: 0 }}>
            Cargar Declaración de Importación (DIM)
          </h3>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#606075', padding: '4px' }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Drop zone / file selector */}
        {!uploading && !result && (
          <label style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            gap: '10px', padding: '32px',
            border: '2px dashed rgba(96,165,250,0.3)', borderRadius: '12px',
            cursor: 'pointer', background: 'rgba(96,165,250,0.03)',
            transition: 'all 0.2s',
          }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(96,165,250,0.6)'; e.currentTarget.style.background = 'rgba(96,165,250,0.06)'; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(96,165,250,0.3)'; e.currentTarget.style.background = 'rgba(96,165,250,0.03)'; }}
          >
            <FileUp size={32} style={{ color: '#60a5fa' }} />
            <div style={{ textAlign: 'center' }}>
              <p style={{ color: '#fff', fontWeight: 600, fontSize: '13px', margin: '0 0 4px' }}>
                Seleccioná el archivo DIM
              </p>
              <p style={{ color: '#606075', fontSize: '11px', margin: 0 }}>
                Solo archivos .pdf
              </p>
            </div>
            <input
              type="file"
              accept=".pdf"
              onChange={handleFileChange}
              style={{ display: 'none' }}
            />
          </label>
        )}

        {/* Spinner de carga */}
        {uploading && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px', padding: '32px 0' }}>
            <div style={{
              width: 36, height: 36, borderRadius: '50%',
              border: '3px solid rgba(96,165,250,0.2)',
              borderTop: '3px solid #60a5fa',
              animation: 'spin 0.8s linear infinite',
            }} />
            <p style={{ color: '#606075', fontSize: '12px', margin: 0 }}>Procesando DIM...</p>
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          </div>
        )}

        {/* Resultado */}
        {result && !uploading && (
          result.error ? (
            <div style={{
              display: 'flex', alignItems: 'flex-start', gap: '10px',
              background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)',
              borderRadius: '10px', padding: '14px',
            }}>
              <AlertCircle size={16} style={{ color: '#f87171', flexShrink: 0, marginTop: '1px' }} />
              <div>
                <p style={{ color: '#f87171', fontWeight: 700, fontSize: '12px', margin: '0 0 2px' }}>Error al procesar</p>
                <p style={{ color: '#f87171', fontSize: '11px', margin: 0, opacity: 0.8 }}>{result.error}</p>
              </div>
            </div>
          ) : (
            <div style={{
              background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)',
              borderRadius: '10px', padding: '16px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
                <CheckCircle size={15} style={{ color: '#22c55e' }} />
                <span style={{ color: '#22c55e', fontWeight: 700, fontSize: '12px' }}>DIM PROCESADA CORRECTAMENTE</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div style={{ textAlign: 'center', padding: '10px', background: 'rgba(34,197,94,0.06)', borderRadius: '8px' }}>
                  <p style={{ color: '#22c55e', fontWeight: 800, fontSize: '22px', margin: 0 }}>
                    {result.matched ?? 0}
                  </p>
                  <p style={{ color: '#606075', fontSize: '10px', margin: '2px 0 0', fontWeight: 600 }}>Certificados generados</p>
                </div>
                <div style={{ textAlign: 'center', padding: '10px', background: 'rgba(249,115,22,0.06)', borderRadius: '8px' }}>
                  <p style={{ color: '#f97316', fontWeight: 800, fontSize: '22px', margin: 0 }}>
                    {result.unmatched ?? 0}
                  </p>
                  <p style={{ color: '#606075', fontSize: '10px', margin: '2px 0 0', fontWeight: 600 }}>VINs no encontrados</p>
                </div>
              </div>
              {result.vins_not_found?.length > 0 && (
                <p style={{ color: '#f87171', fontSize: '11px', margin: '10px 0 0' }}>
                  {result.vins_not_found.length} VIN(s) sin match: {result.vins_not_found.join(', ')}
                </p>
              )}
            </div>
          )
        )}

        {/* Acciones */}
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            style={{
              padding: '8px 18px', borderRadius: '8px',
              border: '1px solid rgba(255,255,255,0.08)',
              background: 'transparent', color: '#606075',
              cursor: 'pointer', fontSize: '12px', fontWeight: 600,
            }}
          >
            {result ? 'Cerrar' : 'Cancelar'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Modal de edición de unidad
// ---------------------------------------------------------------------------
function EditUnitModal({ unit, onSave, onClose, saving, userRole }) {
  const [form, setForm] = useState({
    model: unit.model || '',
    vin_number: unit.vin_number || '',
    engine_number: unit.engine_number || '',
    model_year: unit.model_year || '',
    color: unit.color || '',
    shipment_order_id: '',
  });
  const [orders, setOrders] = useState([]);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [colorOptions, setColorOptions] = useState([]);
  const [colorsLoading, setColorsLoading] = useState(true);

  useEffect(() => {
    if (userRole !== 'superadmin') return;
    setOrdersLoading(true);
    authFetch(`${getApiUrl()}/imports/shipment-orders?is_spare_part=false&page_size=200`)
      .then(r => r.json())
      .then(data => setOrders(data.items || []))
      .catch(() => {})
      .finally(() => setOrdersLoading(false));
  }, [userRole]);

  useEffect(() => {
    setColorsLoading(true);
    authFetch(`${getApiUrl()}/color-runt-mappings`)
      .then(r => r.json())
      .then(data => setColorOptions(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setColorsLoading(false));
  }, []);

  const handleChange = (field, value) => setForm(f => ({ ...f, [field]: value }));

  const labelStyle = { display: 'block', color: '#9ca3af', fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '5px' };
  const inputStyle = {
    width: '100%', padding: '8px 10px', borderRadius: '8px', boxSizing: 'border-box',
    background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
    color: '#fff', fontSize: '12px', outline: 'none',
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1100,
      background: 'rgba(0,0,0,0.78)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: '#13131a', border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '16px', padding: '28px', width: '420px', maxWidth: '94vw',
        display: 'flex', flexDirection: 'column', gap: '18px',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ color: '#fff', fontWeight: 700, fontSize: '15px', margin: 0 }}>
            Editar unidad
          </h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#606075', padding: '4px' }}>
            <X size={18} />
          </button>
        </div>

        {/* Info contextual */}
        <div style={{ background: 'rgba(96,165,250,0.06)', borderRadius: '8px', padding: '10px 12px' }}>
          <p style={{ margin: 0, fontSize: '10px', color: '#60a5fa', fontWeight: 700 }}>{unit.pi_number} — {unit.model || '—'}</p>
        </div>

        {/* Campos */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div>
            <label style={labelStyle}>Modelo</label>
            <input style={inputStyle} value={form.model} onChange={e => handleChange('model', e.target.value)} placeholder="Ej: Xpeed 150" />
          </div>
          <div>
            <label style={labelStyle}>VIN No.</label>
            <input style={inputStyle} value={form.vin_number} onChange={e => handleChange('vin_number', e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}>Motor No.</label>
            <input style={inputStyle} value={form.engine_number} onChange={e => handleChange('engine_number', e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}>Color</label>
            <select
              style={{ ...inputStyle, cursor: colorsLoading ? 'wait' : 'pointer' }}
              value={form.color}
              onChange={e => handleChange('color', e.target.value)}
              disabled={colorsLoading}
            >
              <option value="" style={{ background: '#1e1e2e', color: '#fff' }}>— Sin cambio —</option>
              {colorOptions.map(c => (
                <option key={c.color_key} value={c.color_original} style={{ background: '#1e1e2e', color: '#fff' }}>
                  {c.color_original}{c.nombre_runt ? ` → ${c.nombre_runt}` : ''}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label style={labelStyle}>Año Modelo</label>
            <input
              style={inputStyle}
              type="number"
              value={form.model_year}
              onChange={e => handleChange('model_year', e.target.value)}
              placeholder="Ej: 2025"
            />
          </div>

          {/* Cambiar pedido — solo superadmin */}
          {userRole === 'superadmin' && (
            <div>
              <label style={labelStyle}>Mover a otro pedido</label>
              <select
                style={{ ...inputStyle, cursor: ordersLoading ? 'wait' : 'pointer' }}
                value={form.shipment_order_id}
                onChange={e => handleChange('shipment_order_id', e.target.value)}
                disabled={ordersLoading}
              >
                <option value="" style={{ background: '#1e1e2e', color: '#fff' }}>— Sin cambio —</option>
                {orders
                  .filter(o => o.id !== unit.shipment_order_id)
                  .map(o => (
                    <option key={o.id} value={o.id} style={{ background: '#1e1e2e', color: '#fff' }}>
                      {o.pi_number} — {o.model}{o.cycle ? ` (C${o.cycle})` : ''}
                    </option>
                  ))}
              </select>
              {form.shipment_order_id && (
                <p style={{ margin: '5px 0 0', fontSize: '10px', color: '#fbbf24' }}>
                  ⚠ La unidad se moverá al pedido seleccionado.
                </p>
              )}
            </div>
          )}
        </div>

        {/* Acciones */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
          <button
            onClick={onClose}
            disabled={saving}
            style={{
              padding: '8px 16px', borderRadius: '8px',
              border: '1px solid rgba(255,255,255,0.08)',
              background: 'transparent', color: '#606075',
              cursor: saving ? 'not-allowed' : 'pointer', fontSize: '12px', fontWeight: 600,
            }}
          >
            Cancelar
          </button>
          <button
            onClick={() => onSave(unit.id, form)}
            disabled={saving}
            style={{
              padding: '8px 18px', borderRadius: '8px', border: 'none',
              background: saving ? 'rgba(96,165,250,0.4)' : '#60a5fa',
              color: '#0d0d14', fontSize: '12px', fontWeight: 700,
              cursor: saving ? 'not-allowed' : 'pointer',
            }}
          >
            {saving ? 'Guardando...' : 'Guardar'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Modal de selección de distribuidor para envío físico
// ---------------------------------------------------------------------------
function SeleccionarDistribuidorModal({ onConfirm, onClose }) {
  const [distribuidores, setDistribuidores] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const res = await authFetch(`${getApiUrl()}/imports/distribuidores-venta`);
        const data = await res.json();
        setDistribuidores(data || []);
      } catch {
        setDistribuidores([]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const filtrados = distribuidores.filter(d =>
    d.name.toLowerCase().includes(search.toLowerCase()) ||
    (d.ciudad || '').toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1200,
      background: 'rgba(0,0,0,0.80)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: '#13131a', border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '16px', padding: '28px', width: '480px', maxWidth: '94vw',
        display: 'flex', flexDirection: 'column', gap: '18px', maxHeight: '85vh',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h3 style={{ color: '#fff', fontWeight: 700, fontSize: '15px', margin: '0 0 3px' }}>
              Seleccionar distribuidor destino
            </h3>
            <p style={{ color: '#606075', fontSize: '11px', margin: 0 }}>
              ¿A qué punto de venta se envía el empadronamiento físico?
            </p>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#606075', padding: '4px' }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Buscador */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '8px',
          padding: '8px 12px', borderRadius: '8px',
          background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
        }}>
          <Search size={13} color="#606075" />
          <input
            placeholder="Buscar distribuidor o ciudad..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            autoFocus
            style={{ background: 'none', border: 'none', color: '#fff', fontSize: '12px', outline: 'none', flex: 1 }}
          />
        </div>

        {/* Lista */}
        <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px', flex: 1 }}>
          {loading ? (
            <p style={{ color: '#606075', fontSize: '12px', textAlign: 'center', margin: '24px 0' }}>
              Cargando distribuidores...
            </p>
          ) : filtrados.length === 0 ? (
            <p style={{ color: '#606075', fontSize: '12px', textAlign: 'center', margin: '24px 0' }}>
              No hay distribuidores con venta de motos activos
            </p>
          ) : filtrados.map(d => (
            <button
              key={d.id}
              onClick={() => setSelected(d)}
              style={{
                display: 'flex', alignItems: 'center', gap: '12px',
                padding: '10px 14px', borderRadius: '10px', border: 'none', cursor: 'pointer',
                textAlign: 'left', transition: 'all 0.15s',
                background: selected?.id === d.id
                  ? 'rgba(96,165,250,0.15)'
                  : 'rgba(255,255,255,0.03)',
                outline: selected?.id === d.id
                  ? '1.5px solid rgba(96,165,250,0.5)'
                  : '1px solid rgba(255,255,255,0.06)',
              }}
            >
              <div style={{
                width: 32, height: 32, borderRadius: '8px', flexShrink: 0,
                background: selected?.id === d.id ? 'rgba(96,165,250,0.2)' : 'rgba(255,255,255,0.05)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Send size={14} color={selected?.id === d.id ? '#60a5fa' : '#606075'} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{
                  margin: 0, fontSize: '12px', fontWeight: 700,
                  color: selected?.id === d.id ? '#60a5fa' : '#e2e8f0',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                }}>
                  {d.name}
                </p>
                {(d.ciudad || d.departamento) && (
                  <p style={{ margin: '2px 0 0', fontSize: '10px', color: '#606075', display: 'flex', alignItems: 'center', gap: '3px' }}>
                    <MapPin size={9} />
                    {[d.ciudad, d.departamento].filter(Boolean).join(', ')}
                  </p>
                )}
              </div>
              {selected?.id === d.id && (
                <CheckCircle size={15} color="#60a5fa" style={{ flexShrink: 0 }} />
              )}
            </button>
          ))}
        </div>

        {/* Acciones */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '16px' }}>
          <button
            onClick={onClose}
            style={{
              padding: '8px 16px', borderRadius: '8px',
              border: '1px solid rgba(255,255,255,0.08)',
              background: 'transparent', color: '#606075',
              cursor: 'pointer', fontSize: '12px', fontWeight: 600,
            }}
          >
            Cancelar
          </button>
          <button
            onClick={() => selected && onConfirm(selected)}
            disabled={!selected}
            style={{
              padding: '8px 20px', borderRadius: '8px', border: 'none',
              background: selected ? '#60a5fa' : 'rgba(96,165,250,0.2)',
              color: selected ? '#0d0d14' : '#404060',
              fontSize: '12px', fontWeight: 700,
              cursor: selected ? 'pointer' : 'not-allowed',
              transition: 'all 0.15s',
            }}
          >
            Confirmar envío
          </button>
        </div>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// MotocicletasTab — componente principal
// ---------------------------------------------------------------------------
export default function MotocicletasTab({ userRole }) {
  const [units, setUnits] = useState([]);
  const [total, setTotal] = useState(0);
  const [totalGlobal, setTotalGlobal] = useState(0);
  const [totalEmpadronados, setTotalEmpadronados] = useState(0);
  const [totalPendientes, setTotalPendientes] = useState(0);
  const [totalFacturadas, setTotalFacturadas] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);

  // Filtros
  const [filterPI, setFilterPI] = useState('');
  const [filterModel, setFilterModel] = useState('');
  const [filterVIN, setFilterVIN] = useState('');
  const [filterEngine, setFilterEngine] = useState('');
  const [filterCertificado, setFilterCertificado] = useState(''); // '', 'true', 'false'
  const [filterObservation, setFilterObservation] = useState(''); // '' | observation uuid
  const [filterEnviado, setFilterEnviado] = useState(''); // '', 'true', 'false'
  const [filterFacturado, setFilterFacturado] = useState(''); // '', 'true', 'false'
  const [filterCargadoRunt, setFilterCargadoRunt] = useState(''); // '', 'true', 'false'

  // DIM upload
  const [showDimUpload, setShowDimUpload] = useState(false);
  const [dimUploading, setDimUploading] = useState(false);
  const [dimResult, setDimResult] = useState(null);

  // Edición inline
  const [editUnit, setEditUnit] = useState(null);
  const [deleteUnit, setDeleteUnit] = useState(null);
  const [editSaving, setEditSaving] = useState(false);

  // Error modal para certificado
  const [certError, setCertError] = useState('');
  const [pendingConfirm, setPendingConfirm] = useState(null);

  // Toggle empadronamiento físico
  const [toggling, setToggling] = useState(null); // id de la unidad en proceso
  const [unitPendienteEnvio, setUnitPendienteEnvio] = useState(null); // unidad esperando selección de distribuidor

  // Ubicaciones / bodegas
  const [locations, setLocations] = useState([]);
  const [locationSaving, setLocationSaving] = useState(null);
  // Observaciones predefinidas
  const [observations, setObservations] = useState([]);

  const PAGE_SIZE = 50;
  const [exportingMotos, setExportingMotos] = useState(false);

  const handleExportMotos = async () => {
    setExportingMotos(true);
    try {
      const params = new URLSearchParams();
      if (filterPI) params.append('pi_number', filterPI);
      if (filterModel) params.append('model', filterModel);
      if (filterVIN) params.append('vin', filterVIN);
      if (filterEngine) params.append('engine', filterEngine);
      if (filterCertificado !== '') params.append('certificado_generado', filterCertificado);
      if (filterObservation !== '') params.append('observation_id', filterObservation);
      if (filterEnviado !== '') params.append('empadronamiento_fisico_enviado', filterEnviado);
      if (filterFacturado !== '') params.append('facturado', filterFacturado);
      if (filterCargadoRunt !== '') params.append('cargado_runt', filterCargadoRunt);
      const res = await authFetch(`${getApiUrl()}/imports/moto-units/export?${params}`);
      if (!res.ok) return;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `motocicletas_${new Date().toISOString().slice(0, 10)}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Error exportando motocicletas:', e);
    } finally {
      setExportingMotos(false);
    }
  };

  const fetchUnits = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page, page_size: PAGE_SIZE });
      if (filterPI) params.append('pi_number', filterPI);
      if (filterModel) params.append('model', filterModel);
      if (filterVIN) params.append('vin', filterVIN);
      if (filterEngine) params.append('engine', filterEngine);
      if (filterCertificado !== '') params.append('certificado_generado', filterCertificado);
      if (filterObservation !== '') params.append('observation_id', filterObservation);
      if (filterEnviado !== '') params.append('empadronamiento_fisico_enviado', filterEnviado);
      if (filterFacturado !== '') params.append('facturado', filterFacturado);
      if (filterCargadoRunt !== '') params.append('cargado_runt', filterCargadoRunt);
      const res = await authFetch(`${getApiUrl()}/imports/moto-units?${params}`);
      const data = await res.json();
      setUnits(data.items || []);
      setTotal(data.total || 0);
      setTotalGlobal(data.total_global ?? data.total ?? 0);
      setTotalEmpadronados(data.total_empadronados ?? 0);
      setTotalPendientes(data.total_pendientes ?? 0);
      setTotalFacturadas(data.total_facturadas ?? 0);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [page, filterPI, filterModel, filterVIN, filterEngine, filterCertificado, filterObservation, filterEnviado, filterFacturado, filterCargadoRunt]);

  const fetchLocations = useCallback(async () => {
    try {
      const res = await authFetch(`${getApiUrl()}/imports/moto-locations`);
      const data = await res.json();
      setLocations(Array.isArray(data) ? data : []);
    } catch { setLocations([]); }
  }, []);

  const fetchObservations = useCallback(async () => {
    try {
      const res = await authFetch(`${getApiUrl()}/imports/moto-observations`);
      const data = await res.json();
      setObservations(Array.isArray(data) ? data : []);
    } catch { setObservations([]); }
  }, []);

  useEffect(() => { fetchUnits(); fetchLocations(); fetchObservations(); }, [fetchUnits, fetchLocations, fetchObservations]);

  const handleDimUpload = async (file) => {
    setDimUploading(true);
    setDimResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await authFetch(`${getApiUrl()}/imports/moto-units/dim`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) {
        setDimResult({ error: data.detail || 'Error al procesar el DIM' });
      } else {
        setDimResult(data);
        fetchUnits();
      }
    } catch (e) {
      setDimResult({ error: 'Error de conexión' });
    } finally {
      setDimUploading(false);
    }
  };

  const handleEditSave = async (unitId, form) => {
    setEditSaving(true);
    try {
      const payload = {};
      if (form.model.trim()) payload.model = form.model.trim();
      if (form.vin_number.trim()) payload.vin_number = form.vin_number.trim();
      if (form.engine_number.trim()) payload.engine_number = form.engine_number.trim();
      if (form.model_year !== '' && form.model_year !== null) {
        const y = parseInt(form.model_year, 10);
        if (!isNaN(y)) payload.model_year = y;
      }
      if (form.color) payload.color = form.color;
      if (form.shipment_order_id) payload.shipment_order_id = form.shipment_order_id;
      const res = await authFetch(`${getApiUrl()}/imports/moto-units/${unitId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json();
        toast.error(err.detail || 'Error al guardar');
        return;
      }
      setEditUnit(null);
      fetchUnits();
    } catch (e) {
      toast.error('Error de conexión');
    } finally {
      setEditSaving(false);
    }
  };

  const handleDeleteUnit = (unit) => setDeleteUnit(unit);

  const handleConfirmDelete = async () => {
    if (!deleteUnit) return;
    const unit = deleteUnit;
    setDeleteUnit(null);
    try {
      const res = await authFetch(`${getApiUrl()}/imports/moto-units/${unit.id}`, { method: 'DELETE' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Error al eliminar la unidad');
        return;
      }
      fetchUnits();
    } catch {
      toast.error('Error de conexión');
    }
  };

  const handleToggleEmpadronamiento = (unit) => {
    if (toggling) return;
    if (!unit.empadronamiento_fisico_enviado) {
      // Abre el popup para seleccionar distribuidor
      setUnitPendienteEnvio(unit);
    } else {
      // Ya está enviado → desmarcar directo
      _patchEmpadronamiento(unit.id, { empadronamiento_fisico_enviado: false });
    }
  };

  const handleConfirmarEnvio = async (distribuidor) => {
    if (!unitPendienteEnvio) return;
    const unitId = unitPendienteEnvio.id;
    setUnitPendienteEnvio(null);
    await _patchEmpadronamiento(unitId, {
      empadronamiento_fisico_enviado: true,
      empadronamiento_fisico_distribuidor_id: distribuidor.id,
    });
  };

  const _patchEmpadronamiento = async (unitId, payload) => {
    setToggling(unitId);
    try {
      const res = await authFetch(`${getApiUrl()}/imports/moto-units/${unitId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json();
        toast.error(err.detail || 'Error al actualizar');
        return;
      }
      const data = await res.json();
      setUnits(prev => prev.map(u =>
        u.id === unitId
          ? {
              ...u,
              empadronamiento_fisico_enviado: data.empadronamiento_fisico_enviado,
              empadronamiento_fisico_fecha: data.empadronamiento_fisico_fecha,
              empadronamiento_fisico_distribuidor_id: data.empadronamiento_fisico_distribuidor_id,
              empadronamiento_fisico_distribuidor_nombre: data.empadronamiento_fisico_distribuidor_nombre,
            }
          : u
      ));
    } catch {
      toast.error('Error de conexión');
    } finally {
      setToggling(null);
    }
  };

  const handleDownloadCertificado = async (unit) => {
    try {
      const res = await authFetch(`${getApiUrl()}/imports/moto-units/${unit.id}/certificado`);
      if (!res.ok) {
        const err = await res.json();
        setCertError(err.detail || 'Error al generar el certificado.');
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Certificado_${unit.vin_number}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setCertError('Error de conexión al descargar el certificado.');
    }
  };

  const handleDeleteCertificado = (unit) => {
    setPendingConfirm({
      title: 'Anular empadronamiento',
      message: `¿Anular el empadronamiento de VIN ${unit.vin_number || unit.id}? Esta acción no se puede deshacer.`,
      danger: true,
      confirmLabel: 'Sí, anular',
      action: async () => {
        try {
          const res = await authFetch(`${getApiUrl()}/imports/moto-units/${unit.id}/certificado`, { method: 'DELETE' });
          if (!res.ok) {
            const err = await res.json();
            toast.error(err.detail || 'Error al anular el empadronamiento');
            return;
          }
          setUnits(prev => prev.map(u =>
            u.id === unit.id ? { ...u, certificado_generado: false, certificado_fecha: null } : u
          ));
        } catch {
          toast.error('Error de conexión');
        }
      },
    });
  };

  const handleOpenDim = (unit) => {
    const token = sessionStorage.getItem('um_token');
    const url = `${getApiUrl()}/imports/moto-units/${unit.id}/dim-url?token=${token}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>

      <ErrorModal message={certError} onClose={() => setCertError('')} />

      {/* KPIs — totales globales del backend */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px' }}>
        {[
          { label: 'Total unidades', value: totalGlobal, color: '#60a5fa' },
          { label: 'Empadronadas', value: totalEmpadronados, color: '#22c55e' },
          { label: 'Pendientes', value: totalPendientes, color: '#f97316' },
          { label: 'Facturadas', value: totalFacturadas, color: '#a78bfa' },
        ].map(({ label, value, color }) => (
          <div key={label} style={{ padding: '14px 16px', borderRadius: '10px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
            <p style={{ margin: 0, fontSize: '18px', fontWeight: 800, color }}>{value}</p>
            <p style={{ margin: '2px 0 0', fontSize: '10px', color: '#606075', fontWeight: 600 }}>{label}</p>
          </div>
        ))}
      </div>

      {/* Toolbar */}
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
        {/* PI Number */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '6px',
          padding: '6px 10px', borderRadius: '8px',
          background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)',
          minWidth: 160,
        }}>
          <Search size={11} color="#606075" />
          <input
            placeholder="Buscar PI Number..."
            value={filterPI}
            onChange={e => { setFilterPI(e.target.value); setPage(1); }}
            style={{ background: 'none', border: 'none', color: '#fff', fontSize: '11px', outline: 'none', flex: 1 }}
          />
        </div>

        {/* Modelo */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '6px',
          padding: '6px 10px', borderRadius: '8px',
          background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)',
          minWidth: 140,
        }}>
          <Search size={11} color="#606075" />
          <input
            placeholder="Buscar modelo..."
            value={filterModel}
            onChange={e => { setFilterModel(e.target.value); setPage(1); }}
            style={{ background: 'none', border: 'none', color: '#fff', fontSize: '11px', outline: 'none', flex: 1 }}
          />
        </div>

        {/* VIN */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '6px',
          padding: '6px 10px', borderRadius: '8px',
          background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)',
          minWidth: 150,
        }}>
          <Search size={11} color="#606075" />
          <input
            placeholder="Buscar VIN..."
            value={filterVIN}
            onChange={e => { setFilterVIN(e.target.value); setPage(1); }}
            style={{ background: 'none', border: 'none', color: '#fff', fontSize: '11px', outline: 'none', flex: 1 }}
          />
        </div>

        {/* Motor */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '6px',
          padding: '6px 10px', borderRadius: '8px',
          background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)',
          minWidth: 150,
        }}>
          <Search size={11} color="#606075" />
          <input
            placeholder="Buscar No. Motor..."
            value={filterEngine}
            onChange={e => { setFilterEngine(e.target.value); setPage(1); }}
            style={{ background: 'none', border: 'none', color: '#fff', fontSize: '11px', outline: 'none', flex: 1 }}
          />
        </div>

        {/* Filtro empadronamiento */}
        <select
          value={filterCertificado}
          onChange={e => { setFilterCertificado(e.target.value); setPage(1); }}
          style={{
            padding: '6px 10px', borderRadius: '8px',
            background: '#1a1a24', border: '1px solid rgba(255,255,255,0.08)',
            color: filterCertificado === '' ? '#606075' : '#fff',
            fontSize: '11px', outline: 'none',
          }}
        >
          <option value="">Todos</option>
          <option value="true">Empadronados</option>
          <option value="false">Pendientes</option>
        </select>

        {/* Filtro observación */}
        <select
          value={filterObservation}
          onChange={e => { setFilterObservation(e.target.value); setPage(1); }}
          style={{
            padding: '6px 10px', borderRadius: '8px',
            background: '#1a1a24', border: '1px solid rgba(255,255,255,0.08)',
            color: filterObservation === '' ? '#606075' : '#fff',
            fontSize: '11px', outline: 'none',
          }}
        >
          <option value="">Todas (Observación)</option>
          {observations.map(obs => (
            <option key={obs.id} value={obs.id}>{obs.name}</option>
          ))}
        </select>

        {/* Filtro enviado */}
        <select
          value={filterEnviado}
          onChange={e => { setFilterEnviado(e.target.value); setPage(1); }}
          style={{
            padding: '6px 10px', borderRadius: '8px',
            background: '#1a1a24', border: '1px solid rgba(255,255,255,0.08)',
            color: filterEnviado === '' ? '#606075' : '#fff',
            fontSize: '11px', outline: 'none',
          }}
        >
          <option value="">Todos (Enviado)</option>
          <option value="true">Enviado</option>
          <option value="false">No enviado</option>
        </select>

        {/* Filtro facturado */}
        <select
          value={filterFacturado}
          onChange={e => { setFilterFacturado(e.target.value); setPage(1); }}
          style={{
            padding: '6px 10px', borderRadius: '8px',
            background: '#1a1a24', border: '1px solid rgba(255,255,255,0.08)',
            color: filterFacturado === '' ? '#606075' : '#fff',
            fontSize: '11px', outline: 'none',
          }}
        >
          <option value="">Todos (Facturado)</option>
          <option value="true">Facturado</option>
          <option value="false">No facturado</option>
        </select>

        {/* Filtro cargado RUNT */}
        <select
          value={filterCargadoRunt}
          onChange={e => { setFilterCargadoRunt(e.target.value); setPage(1); }}
          style={{
            padding: '6px 10px', borderRadius: '8px',
            background: '#1a1a24', border: '1px solid rgba(255,255,255,0.08)',
            color: filterCargadoRunt === '' ? '#606075' : '#fff',
            fontSize: '11px', outline: 'none',
          }}
        >
          <option value="">Todos (RUNT)</option>
          <option value="true">Cargado RUNT</option>
          <option value="false">No cargado RUNT</option>
        </select>

        {/* Refresh */}
        <button
          onClick={() => fetchUnits()}
          style={{ padding: '6px 8px', borderRadius: '8px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.07)', cursor: 'pointer', color: '#9ca3af' }}
        >
          <RefreshCw size={13} />
        </button>

        {/* Cargar DIM — superadmin y administrador */}
        {(userRole === 'superadmin' || userRole === 'administrativo') && (
          <button
            onClick={() => { setDimResult(null); setShowDimUpload(true); }}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '7px 14px', borderRadius: '8px', border: 'none',
              background: 'rgba(96,165,250,0.12)', color: '#60a5fa',
              fontSize: '11px', fontWeight: 700, cursor: 'pointer',
              letterSpacing: '0.04em',
            }}
          >
            <FileUp size={13} /> Cargar DIM
          </button>
        )}

        {/* Exportar Excel (solo superadmin) */}
        {userRole === 'superadmin' && (
          <button
            onClick={handleExportMotos}
            disabled={exportingMotos}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '7px 14px', borderRadius: '8px', border: 'none',
              background: exportingMotos ? 'rgba(34,197,94,0.06)' : 'rgba(34,197,94,0.12)',
              color: exportingMotos ? '#606075' : '#22c55e',
              fontSize: '11px', fontWeight: 700, cursor: exportingMotos ? 'not-allowed' : 'pointer',
              letterSpacing: '0.04em',
            }}
          >
            <FileSpreadsheet size={13} />
            {exportingMotos ? 'Exportando...' : 'Exportar Excel'}
          </button>
        )}

        {/* Contador */}
        <span style={{ fontSize: '11px', color: '#606075', marginLeft: 'auto' }}>
          {total} unidad{total !== 1 ? 'es' : ''} encontrada{total !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Tabla */}
      {loading ? (
        <p style={{ color: '#606075', fontSize: '12px', textAlign: 'center', margin: '40px 0' }}>Cargando unidades...</p>
      ) : units.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#606075' }}>
          <Bike size={36} style={{ margin: '0 auto 12px', display: 'block', opacity: 0.3 }} />
          <p style={{ fontSize: '13px', margin: 0 }}>No hay unidades cargadas</p>
          <p style={{ fontSize: '11px', margin: '4px 0 0', color: '#404050' }}>
            Importá un Packing List de Motos para ver las unidades
          </p>
        </div>
      ) : (
        <div style={{ overflowX: 'auto', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.06)' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
            <thead>
              <tr style={{ background: '#0e0e14' }}>
                {['PI Number', 'Modelo', 'VIN', 'Motor No.', 'Color RUNT', 'Año Modelo', 'No. Levante', 'Ubicación', 'Naciol.', 'Observación', 'Empadronamiento', 'Gestión Distribuidor', 'Acciones'].map(h => (
                  <th
                    key={h}
                    style={{
                      padding: '9px 12px', textAlign: 'left',
                      fontSize: '9px', fontWeight: 700, color: '#606075',
                      textTransform: 'uppercase', letterSpacing: '0.07em',
                      borderBottom: '1px solid rgba(255,255,255,0.06)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {units.map((unit) => (
                <tr
                  key={unit.id}
                  style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <td style={{ padding: '9px 12px', color: '#60a5fa', fontWeight: 700, fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                    {unit.pi_number || '—'}
                  </td>
                  <td style={{ padding: '9px 12px', color: '#e2e8f0', whiteSpace: 'nowrap' }}>
                    {unit.model || unit.modelo || '—'}
                  </td>
                  <td style={{ padding: '9px 12px', color: '#d1d5db', fontFamily: 'monospace', fontSize: '10px', whiteSpace: 'nowrap' }}>
                    {unit.vin_number || unit.vin || '—'}
                  </td>
                  <td style={{ padding: '9px 12px', color: '#9ca3af', fontFamily: 'monospace', fontSize: '10px', whiteSpace: 'nowrap' }}>
                    {unit.engine_number || unit.motor_number || '—'}
                  </td>
                  <td style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
                    {unit.color_runt
                      ? <span style={{ fontSize: '10px', fontWeight: 700, padding: '2px 7px', borderRadius: '20px', background: 'rgba(99,102,241,0.1)', color: '#818cf8', border: '1px solid rgba(99,102,241,0.25)' }}>{unit.color_runt}</span>
                      : <span style={{ fontSize: '10px', fontWeight: 700, padding: '2px 7px', borderRadius: '20px', background: 'rgba(248,113,113,0.1)', color: '#f87171', border: '1px solid rgba(248,113,113,0.25)' }}>Sin mapeo</span>
                    }
                  </td>
                  <td style={{ padding: '9px 12px', color: '#9ca3af', whiteSpace: 'nowrap' }}>
                    {unit.model_year || '—'}
                  </td>
                  <td style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
                    {unit.no_lev
                      ? <span style={{ fontFamily: 'monospace', fontSize: '10px', color: '#a78bfa', fontWeight: 700 }}>{unit.no_lev}</span>
                      : <span style={{ color: '#404050', fontSize: '10px' }}>—</span>
                    }
                  </td>
                  <td style={{ padding: '9px 12px' }}>
                    <select
                      value={unit.location_id || ''}
                      disabled={locationSaving === unit.id}
                      onChange={async (e) => {
                        const locId = e.target.value || null;
                        setLocationSaving(unit.id);
                        try {
                          const res = await authFetch(`${getApiUrl()}/imports/moto-units/${unit.id}`, {
                            method: 'PATCH',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ location_id: locId }),
                          });
                          if (res.ok) {
                            const data = await res.json();
                            setUnits(prev => prev.map(u => u.id === unit.id ? { ...u, location_id: data.location_id, location_name: data.location_name } : u));
                          }
                        } finally { setLocationSaving(null); }
                      }}
                      style={{
                        background: unit.location_id ? 'rgba(167,139,250,0.1)' : '#1a1a24',
                        border: `1px solid ${unit.location_id ? 'rgba(167,139,250,0.3)' : 'rgba(255,255,255,0.08)'}`,
                        borderRadius: '6px', color: unit.location_id ? '#a78bfa' : '#606075',
                        fontSize: '11px', fontWeight: 700, padding: '4px 8px', outline: 'none', cursor: 'pointer',
                      }}
                    >
                      <option value="">— Sin ubicación —</option>
                      {locations.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                    </select>
                  </td>
                  <td style={{ padding: '9px 12px', textAlign: 'center' }}>
                    {(userRole === 'superadmin' || userRole === 'administrativo') ? (
                      <button
                        title={unit.separada_nacionalizacion ? 'Separada para nacionalización — click para liberar' : 'Marcar como separada para nacionalización'}
                        onClick={async () => {
                          const res = await authFetch(`${getApiUrl()}/imports/moto-units/${unit.id}`, {
                            method: 'PATCH', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ separada_nacionalizacion: !unit.separada_nacionalizacion }),
                          });
                          if (res.ok) { const d = await res.json(); setUnits(prev => prev.map(u => u.id === unit.id ? { ...u, separada_nacionalizacion: d.separada_nacionalizacion } : u)); }
                        }}
                        style={{
                          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                          width: 24, height: 24, borderRadius: '50%', border: 'none',
                          cursor: 'pointer', transition: 'all 0.15s',
                          ...(unit.separada_nacionalizacion
                            ? { background: 'rgba(251,191,36,0.18)', color: '#fbbf24', outline: '1px solid rgba(251,191,36,0.5)' }
                            : { background: 'rgba(96,96,117,0.1)', color: '#404050', outline: '1px solid rgba(96,96,117,0.2)' }),
                        }}
                      >
                        <Lock size={13} />
                      </button>
                    ) : (
                      <span title={unit.separada_nacionalizacion ? 'Separada para nacionalización' : ''} style={{
                        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                        width: 24, height: 24, borderRadius: '50%',
                        ...(unit.separada_nacionalizacion
                          ? { background: 'rgba(251,191,36,0.18)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.5)' }
                          : { background: 'transparent', color: '#404050' }),
                      }}>
                        {unit.separada_nacionalizacion && <Lock size={13} />}
                      </span>
                    )}
                  </td>
                  <td style={{ padding: '9px 12px' }}>
                    <select
                      value={unit.observation_id || ''}
                      onChange={async (e) => {
                        const obsId = e.target.value || null;
                        const res = await authFetch(`${getApiUrl()}/imports/moto-units/${unit.id}`, {
                          method: 'PATCH',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ observation_id: obsId }),
                        });
                        if (res.ok) {
                          const data = await res.json();
                          setUnits(prev => prev.map(u => u.id === unit.id ? { ...u, observation_id: data.observation_id, observation_name: data.observation_name } : u));
                        }
                      }}
                      style={{
                        background: unit.observation_id ? 'rgba(251,146,60,0.1)' : '#1a1a24',
                        border: `1px solid ${unit.observation_id ? 'rgba(251,146,60,0.3)' : 'rgba(255,255,255,0.08)'}`,
                        borderRadius: '6px', color: unit.observation_id ? '#fb923c' : '#606075',
                        fontSize: '11px', fontWeight: 700, padding: '4px 8px', outline: 'none', cursor: 'pointer', maxWidth: '160px',
                      }}
                    >
                      <option value="">— Sin observación —</option>
                      {observations.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
                    </select>
                  </td>
                  <td style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <CertBadge generated={unit.certificado_generado} />
                      {unit.certificado_generado && (
                        <button
                          onClick={() => handleDownloadCertificado(unit)}
                          title="Descargar certificado de empadronamiento"
                          style={{
                            display: 'flex', alignItems: 'center', gap: '4px',
                            padding: '3px 8px', borderRadius: '6px', border: 'none',
                            background: 'rgba(34,197,94,0.1)', color: '#22c55e',
                            fontSize: '10px', fontWeight: 700, cursor: 'pointer',
                          }}
                        >
                          <Download size={11} />
                        </button>
                      )}
                      {unit.certificado_generado && (userRole === 'superadmin' || userRole === 'administrativo') && (
                        <button
                          onClick={() => handleDeleteCertificado(unit)}
                          title="Anular empadronamiento"
                          style={{
                            display: 'flex', alignItems: 'center', gap: '4px',
                            padding: '3px 8px', borderRadius: '6px', border: 'none',
                            background: 'rgba(248,113,113,0.1)', color: '#f87171',
                            fontSize: '10px', fontWeight: 700, cursor: 'pointer',
                          }}
                        >
                          <Trash2 size={11} />
                        </button>
                      )}
                      {unit.dim_pdf_object_name && (
                        <button
                          onClick={() => handleOpenDim(unit)}
                          title="Ver Declaración de Importación (DIM)"
                          style={{
                            display: 'flex', alignItems: 'center', gap: '4px',
                            padding: '3px 8px', borderRadius: '6px', border: 'none',
                            background: 'rgba(96,165,250,0.1)', color: '#60a5fa',
                            fontSize: '10px', fontWeight: 700, cursor: 'pointer',
                          }}
                        >
                          <FileText size={11} /> DIM
                        </button>
                      )}
                    </div>
                  </td>
                  <td style={{ padding: '9px 12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '5px', flexWrap: 'nowrap' }}>
                      {/* 1. Enviado */}
                      {(userRole === 'superadmin' || userRole === 'administrativo') ? (
                        <button
                          onClick={() => handleToggleEmpadronamiento(unit)}
                          disabled={toggling === unit.id}
                          title={unit.empadronamiento_fisico_enviado
                            ? `Enviado${unit.empadronamiento_fisico_fecha ? ' el ' + new Date(unit.empadronamiento_fisico_fecha).toLocaleDateString('es-CO') : ''}${unit.empadronamiento_fisico_distribuidor_nombre ? ' a ' + unit.empadronamiento_fisico_distribuidor_nombre : ''} — click para desmarcar`
                            : 'Marcar como enviado al distribuidor'}
                          style={{
                            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                            width: 24, height: 24, borderRadius: '50%', border: 'none',
                            cursor: toggling === unit.id ? 'not-allowed' : 'pointer', transition: 'all 0.15s',
                            ...(unit.empadronamiento_fisico_enviado
                              ? { background: 'rgba(34,197,94,0.12)', color: '#22c55e', outline: '1px solid rgba(34,197,94,0.3)' }
                              : { background: 'rgba(96,96,117,0.12)', color: '#606075', outline: '1px solid rgba(96,96,117,0.25)' }),
                          }}
                        >
                          {toggling === unit.id ? '·' : <Send size={13} />}
                        </button>
                      ) : (
                        <span title={unit.empadronamiento_fisico_enviado ? 'Enviado' : 'Pendiente de envío'} style={{
                          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                          width: 24, height: 24, borderRadius: '50%',
                          ...(unit.empadronamiento_fisico_enviado
                            ? { background: 'rgba(34,197,94,0.1)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.25)' }
                            : { background: 'rgba(96,96,117,0.1)', color: '#404050', border: '1px solid rgba(96,96,117,0.2)' }),
                        }}>
                          <Send size={13} />
                        </span>
                      )}
                      {/* 2. Facturado */}
                      {(userRole === 'superadmin' || userRole === 'administrativo') ? (
                        <button
                          title={unit.facturado ? 'Facturado — click para desmarcar' : 'Marcar como facturado'}
                          onClick={async () => {
                            const res = await authFetch(`${getApiUrl()}/imports/moto-units/${unit.id}`, {
                              method: 'PATCH', headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({ facturado: !unit.facturado }),
                            });
                            if (res.ok) { const d = await res.json(); setUnits(prev => prev.map(u => u.id === unit.id ? { ...u, facturado: d.facturado } : u)); }
                          }}
                          style={{
                            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                            width: 24, height: 24, borderRadius: '50%', border: 'none',
                            cursor: 'pointer', transition: 'all 0.15s',
                            ...(unit.facturado
                              ? { background: 'rgba(59,130,246,0.15)', color: '#3b82f6', outline: '1px solid rgba(59,130,246,0.4)' }
                              : { background: 'rgba(96,96,117,0.1)', color: '#404050', outline: '1px solid rgba(96,96,117,0.2)' }),
                          }}
                        >
                          <Receipt size={13} />
                        </button>
                      ) : (
                        <span title={unit.facturado ? 'Facturado' : 'Sin facturar'} style={{
                          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                          width: 24, height: 24, borderRadius: '50%',
                          ...(unit.facturado
                            ? { background: 'rgba(59,130,246,0.15)', color: '#3b82f6', border: '1px solid rgba(59,130,246,0.4)' }
                            : { background: 'rgba(96,96,117,0.1)', color: '#404050', border: '1px solid rgba(96,96,117,0.2)' }),
                        }}>
                          <Receipt size={13} />
                        </span>
                      )}
                      {/* 3. Cargado RUNT */}
                      {(userRole === 'superadmin' || userRole === 'administrativo') ? (
                        <button
                          title={unit.cargado_runt ? 'Cargado al RUNT — click para desmarcar' : 'Marcar como cargado al RUNT'}
                          onClick={async () => {
                            const res = await authFetch(`${getApiUrl()}/imports/moto-units/${unit.id}`, {
                              method: 'PATCH', headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({ cargado_runt: !unit.cargado_runt }),
                            });
                            if (res.ok) { const d = await res.json(); setUnits(prev => prev.map(u => u.id === unit.id ? { ...u, cargado_runt: d.cargado_runt } : u)); }
                          }}
                          style={{
                            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                            width: 24, height: 24, borderRadius: '50%', border: 'none',
                            cursor: 'pointer', transition: 'all 0.15s',
                            ...(unit.cargado_runt
                              ? { background: 'rgba(59,130,246,0.15)', color: '#3b82f6', outline: '1px solid rgba(59,130,246,0.4)' }
                              : { background: 'rgba(96,96,117,0.1)', color: '#404050', outline: '1px solid rgba(96,96,117,0.2)' }),
                          }}
                        >
                          <ShieldCheck size={13} />
                        </button>
                      ) : (
                        <span title={unit.cargado_runt ? 'Cargado al RUNT' : 'Sin cargar al RUNT'} style={{
                          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                          width: 24, height: 24, borderRadius: '50%',
                          ...(unit.cargado_runt
                            ? { background: 'rgba(59,130,246,0.15)', color: '#3b82f6', border: '1px solid rgba(59,130,246,0.4)' }
                            : { background: 'rgba(96,96,117,0.1)', color: '#404050', border: '1px solid rgba(96,96,117,0.2)' }),
                        }}>
                          <ShieldCheck size={13} />
                        </span>
                      )}
                      {/* Nombre distribuidor — después de los 3 íconos */}
                      {unit.empadronamiento_fisico_distribuidor_nombre && (
                        <span style={{
                          fontSize: '9px', color: '#9ca3af', fontWeight: 600,
                          maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap', display: 'inline-block',
                        }}
                          title={unit.empadronamiento_fisico_distribuidor_nombre}
                        >
                          {unit.empadronamiento_fisico_distribuidor_nombre}
                        </span>
                      )}
                    </div>
                  </td>
                  <td style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
                    <div style={{ display: 'flex', gap: '4px' }}>
                      <button
                        onClick={() => setEditUnit(unit)}
                        title="Editar unidad"
                        style={{
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          padding: '4px 8px', borderRadius: '6px', border: 'none',
                          background: 'rgba(255,255,255,0.06)', color: '#9ca3af',
                          cursor: 'pointer', transition: 'all 0.15s',
                        }}
                        onMouseEnter={e => { e.currentTarget.style.background = 'rgba(96,165,250,0.15)'; e.currentTarget.style.color = '#60a5fa'; }}
                        onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; e.currentTarget.style.color = '#9ca3af'; }}
                      >
                        <Pencil size={12} />
                      </button>
                      {userRole === 'superadmin' && (
                        <button
                          onClick={() => handleDeleteUnit(unit)}
                          title="Eliminar unidad"
                          style={{
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            padding: '4px 8px', borderRadius: '6px', border: 'none',
                            background: 'rgba(255,255,255,0.06)', color: '#9ca3af',
                            cursor: 'pointer', transition: 'all 0.15s',
                          }}
                          onMouseEnter={e => { e.currentTarget.style.background = 'rgba(248,113,113,0.15)'; e.currentTarget.style.color = '#f87171'; }}
                          onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; e.currentTarget.style.color = '#9ca3af'; }}
                        >
                          <Trash2 size={12} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Paginación */}
      {total > PAGE_SIZE && (
        <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', alignItems: 'center' }}>
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            style={{
              padding: '5px 12px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.08)',
              background: 'transparent', color: page === 1 ? '#404050' : '#9ca3af',
              cursor: page === 1 ? 'not-allowed' : 'pointer', fontSize: '11px',
            }}
          >
            ← Anterior
          </button>
          <span style={{ color: '#606075', fontSize: '11px' }}>
            Pág. {page} / {Math.ceil(total / PAGE_SIZE)}
          </span>
          <button
            onClick={() => setPage(p => p + 1)}
            disabled={page >= Math.ceil(total / PAGE_SIZE)}
            style={{
              padding: '5px 12px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.08)',
              background: 'transparent', color: page >= Math.ceil(total / PAGE_SIZE) ? '#404050' : '#9ca3af',
              cursor: page >= Math.ceil(total / PAGE_SIZE) ? 'not-allowed' : 'pointer', fontSize: '11px',
            }}
          >
            Siguiente →
          </button>
        </div>
      )}

      {/* Modal DIM */}
      {showDimUpload && (
        <DimUploadModal
          onUpload={handleDimUpload}
          onClose={() => setShowDimUpload(false)}
          uploading={dimUploading}
          result={dimResult}
        />
      )}

      {/* Modal edición de unidad */}
      {editUnit && (
        <EditUnitModal
          unit={editUnit}
          onSave={handleEditSave}
          onClose={() => setEditUnit(null)}
          saving={editSaving}
          userRole={userRole}
        />
      )}

      {/* Modal confirmación de eliminación */}
      <ConfirmDeleteModal
        unit={deleteUnit}
        onConfirm={handleConfirmDelete}
        onClose={() => setDeleteUnit(null)}
      />

      {/* Modal selección de distribuidor para envío físico */}
      {unitPendienteEnvio && (
        <SeleccionarDistribuidorModal
          onConfirm={handleConfirmarEnvio}
          onClose={() => setUnitPendienteEnvio(null)}
        />
      )}

      {pendingConfirm && (
        <ConfirmModal
          title={pendingConfirm.title}
          message={pendingConfirm.message}
          danger={pendingConfirm.danger}
          confirmLabel={pendingConfirm.confirmLabel}
          onCancel={() => setPendingConfirm(null)}
          onConfirm={() => { setPendingConfirm(null); pendingConfirm.action(); }}
        />
      )}
    </div>
  );
}
