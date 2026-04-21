'use client';
import { useState, useEffect } from 'react';
import AdminLayout from '../admin-layout';
import { Building2, Edit, Save, X, Phone, MapPin, Hash, Plus, Mail, User, Calendar, Wrench, ShoppingCart, Package } from 'lucide-react';
import { authFetch } from '../../lib/authFetch';

const API = () => (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace(/^http:\/\/(?!localhost)/, 'https://');

const NIVEL_CFG = {
  '1S': { color: '#60a5fa', bg: 'rgba(96,165,250,0.12)', border: 'rgba(96,165,250,0.3)' },
  '2S': { color: '#a78bfa', bg: 'rgba(167,139,250,0.12)', border: 'rgba(167,139,250,0.3)' },
  '3S': { color: '#fb923c', bg: 'rgba(251,146,60,0.12)', border: 'rgba(251,146,60,0.3)' },
};

const ESTADO_CFG = {
  activo:     { color: '#22c55e', label: 'Activo' },
  suspendido: { color: '#fb923c', label: 'Suspendido' },
  retirado:   { color: '#f87171', label: 'Retirado' },
};

function NivelBadge({ nivel }) {
  const cfg = NIVEL_CFG[nivel] || { color: '#9ca3af', bg: 'rgba(156,163,175,0.12)', border: 'rgba(156,163,175,0.3)' };
  return (
    <span style={{ fontSize: '10px', fontWeight: 800, padding: '2px 8px', borderRadius: '20px', background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`, letterSpacing: '0.05em' }}>
      {nivel || '—'}
    </span>
  );
}

function CapIcon({ active, icon: Icon, title }) {
  return (
    <span title={title} style={{ opacity: active ? 1 : 0.2 }}>
      <Icon size={13} color={active ? '#fb923c' : '#9ca3af'} />
    </span>
  );
}

function Toggle({ label, checked, onChange }) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', padding: '10px 12px', borderRadius: '8px', background: checked ? 'rgba(251,146,60,0.08)' : 'rgba(255,255,255,0.03)', border: `1px solid ${checked ? 'rgba(251,146,60,0.3)' : 'rgba(255,255,255,0.08)'}`, transition: 'all 0.2s' }}>
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} style={{ accentColor: '#fb923c', width: 14, height: 14 }} />
      <span style={{ fontSize: '11px', fontWeight: 700, color: checked ? '#fb923c' : '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</span>
    </label>
  );
}

const EMPTY_FORM = {
  name: '', nit: '', phone: '', email: '',
  departamento: '', ciudad: '', direccion: '', zona_geografica: '',
  representante_legal: '', fecha_vinculacion: '', categoria: '',
  estado_red: 'activo', tenant_type: 'distribuidor',
  has_sales: false, has_parts: false, has_service: false,
  capacidad_bahias: '', numero_tecnicos: '', tipo_servicio: 'Todos',
};

export default function TenantsPage() {
  const [tenants, setTenants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editForm, setEditForm] = useState(EMPTY_FORM);
  const [departments, setDepartments] = useState([]);
  const [cities, setCities] = useState([]);
  const [saving, setSaving] = useState(false);

  const fetchTenants = async () => {
    setLoading(true);
    try {
      const res = await authFetch('/tenants');
      const data = await res.json();
      setTenants(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error('Error', e);
    } finally {
      setLoading(false);
    }
  };

  const fetchDepartments = async () => {
    try {
      const res = await fetch(`${API()}/tenants/divipola/departments`);
      setDepartments(await res.json());
    } catch (e) { console.error(e); }
  };

  const fetchCities = async (dpto) => {
    if (!dpto) { setCities([]); return; }
    try {
      const res = await fetch(`${API()}/tenants/divipola/cities?departamento=${encodeURIComponent(dpto)}`);
      setCities(await res.json());
    } catch (e) { console.error(e); }
  };

  useEffect(() => { fetchTenants(); fetchDepartments(); }, []);

  const f = (key, val) => setEditForm(prev => ({ ...prev, [key]: val }));

  const openNew = () => {
    setCities([]);
    setEditForm(EMPTY_FORM);
    setShowModal(true);
  };

  const openEdit = (t) => {
    if (t.departamento) fetchCities(t.departamento);
    else setCities([]);
    setEditForm({
      ...EMPTY_FORM, ...t,
      fecha_vinculacion: t.fecha_vinculacion || '',
      capacidad_bahias: t.capacidad_bahias ?? '',
      numero_tecnicos: t.numero_tecnicos ?? '',
      tipo_servicio: t.tipo_servicio || 'Todos',
      estado_red: t.estado_red || 'activo',
    });
    setShowModal(true);
  };

  const saveTenant = async () => {
    setSaving(true);
    try {
      const method = editForm.id ? 'PUT' : 'POST';
      const url = editForm.id ? `/tenants/${editForm.id}` : '/tenants';
      const payload = {
        ...editForm,
        capacidad_bahias: editForm.capacidad_bahias !== '' ? Number(editForm.capacidad_bahias) : null,
        numero_tecnicos: editForm.numero_tecnicos !== '' ? Number(editForm.numero_tecnicos) : null,
        fecha_vinculacion: editForm.fecha_vinculacion || null,
      };
      const res = await authFetch(url, { method, body: JSON.stringify(payload) });
      if (res.ok) { setShowModal(false); fetchTenants(); }
      else { const err = await res.json(); alert(err.detail || 'Error al guardar'); }
    } catch (e) { alert('Error de conexión'); }
    finally { setSaving(false); }
  };

  const computedNivel = () => {
    const n = [editForm.has_sales, editForm.has_parts, editForm.has_service].filter(Boolean).length;
    return n > 0 ? `${n}S` : null;
  };

  return (
    <AdminLayout>
      <header className="page-header">
        <div>
          <h1 className="page-title">Red de <span style={{ fontStyle: 'italic', color: 'var(--accent-orange)', WebkitTextFillColor: 'var(--accent-orange)' }}>Distribución</span></h1>
          <p className="page-subtitle">Puntos de la red nacional UM Colombia · {tenants.length} registrados</p>
        </div>
        <button className="btn-primary" onClick={openNew}>
          <Plus size={16} /> Agregar Punto de Red
        </button>
      </header>

      <div className="tenants-grid">
        {loading ? (
          <div className="glass p-12 text-center col-span-full text-white/50 animate-pulse">Consultando red nacional...</div>
        ) : tenants.map(t => {
          const estado = ESTADO_CFG[t.estado_red] || ESTADO_CFG.activo;
          return (
            <div key={t.id} className="tenant-card relative group">
              <div style={{ height: 4, background: estado.color, position: 'absolute', top: 0, left: 0, right: 0, borderRadius: '16px 16px 0 0' }} />
              <div className="p-5">
                <div className="flex justify-between items-start">
                  <div className="flex items-center gap-3">
                    <div style={{ width: 42, height: 42, borderRadius: 12, background: 'rgba(251,146,60,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(251,146,60,0.2)', flexShrink: 0 }}>
                      <Building2 size={20} color="#fb923c" />
                    </div>
                    <div>
                      <h3 style={{ fontWeight: 900, fontSize: 14, color: '#fff', lineHeight: 1.2, textTransform: 'uppercase', letterSpacing: '-0.01em' }}>{t.name}</h3>
                      <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 4 }}>
                        <NivelBadge nivel={t.nivel_red} />
                        <span style={{ fontSize: 9, color: estado.color, fontWeight: 700, textTransform: 'uppercase' }}>{estado.label}</span>
                        {t.categoria && <span style={{ fontSize: 9, color: '#9ca3af', fontWeight: 700 }}>Cat. {t.categoria}</span>}
                      </div>
                    </div>
                  </div>
                  <button onClick={() => openEdit(t)} className="edit-btn"><Edit size={14} /></button>
                </div>

                {/* Capacidades */}
                <div style={{ display: 'flex', gap: 10, margin: '14px 0 10px', padding: '8px 10px', borderRadius: 8, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)' }}>
                  <CapIcon active={t.has_sales} icon={ShoppingCart} title="Venta de motos" />
                  <CapIcon active={t.has_parts} icon={Package} title="Venta de repuestos" />
                  <CapIcon active={t.has_service} icon={Wrench} title="Servicio de taller" />
                  <span style={{ fontSize: 9, color: '#606075', marginLeft: 'auto', alignSelf: 'center' }}>
                    {[t.has_sales && 'Motos', t.has_parts && 'Repuestos', t.has_service && 'Servicio'].filter(Boolean).join(' · ') || 'Sin capacidades'}
                  </span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {t.nit && <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 11, color: 'rgba(255,255,255,0.6)' }}><Hash size={11} color="rgba(255,255,255,0.2)" /><span style={{ fontFamily: 'monospace' }}>{t.nit}</span></div>}
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 11, color: 'rgba(255,255,255,0.6)' }}><MapPin size={11} color="rgba(255,255,255,0.2)" /><span>{[t.ciudad, t.departamento].filter(Boolean).join(', ') || 'Sin ubicación'}</span></div>
                  {t.phone && <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 11, color: 'rgba(255,255,255,0.6)' }}><Phone size={11} color="rgba(255,255,255,0.2)" /><span style={{ fontFamily: 'monospace' }}>{t.phone}</span></div>}
                  {t.representante_legal && <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 11, color: 'rgba(255,255,255,0.6)' }}><User size={11} color="rgba(255,255,255,0.2)" /><span>{t.representante_legal}</span></div>}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {showModal && (
        <div className="modal-backdrop">
          <div className="modal-box" style={{ maxWidth: 680, maxHeight: '90vh', overflowY: 'auto' }}>
            <div className="modal-head">
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <h2 style={{ fontSize: 14, fontWeight: 900, textTransform: 'uppercase', color: '#fff', letterSpacing: '-0.01em' }}>{editForm.id ? 'Editar Punto de Red' : 'Nuevo Punto de Red'}</h2>
                {computedNivel() && <NivelBadge nivel={computedNivel()} />}
              </div>
              <button onClick={() => setShowModal(false)} className="close-btn"><X size={16} /></button>
            </div>

            <div className="modal-body">
              {/* Capacidades — primero porque determinan el nivel */}
              <p style={{ fontSize: 9, fontWeight: 800, color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 8 }}>Capacidades del punto de red</p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 20 }}>
                <Toggle label="Venta de motos" checked={editForm.has_sales} onChange={v => f('has_sales', v)} />
                <Toggle label="Venta de repuestos" checked={editForm.has_parts} onChange={v => f('has_parts', v)} />
                <Toggle label="Servicio de taller" checked={editForm.has_service} onChange={v => f('has_service', v)} />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                <div style={{ gridColumn: '1 / -1' }}>
                  <label>Razón Social / Nombre *</label>
                  <input value={editForm.name} onChange={e => f('name', e.target.value)} placeholder="Ej: Motors 100 S.A.S" />
                </div>
                <div>
                  <label>NIT</label>
                  <input value={editForm.nit} onChange={e => f('nit', e.target.value)} placeholder="Ej: 900.123.456-1" />
                </div>
                <div>
                  <label>Representante Legal</label>
                  <input value={editForm.representante_legal} onChange={e => f('representante_legal', e.target.value)} placeholder="Nombre completo" />
                </div>
                <div>
                  <label>Teléfono</label>
                  <input value={editForm.phone} onChange={e => f('phone', e.target.value)} placeholder="300 123 4567" />
                </div>
                <div>
                  <label>Email</label>
                  <input type="email" value={editForm.email} onChange={e => f('email', e.target.value)} placeholder="contacto@empresa.com" />
                </div>
                <div>
                  <label>Departamento</label>
                  <select value={editForm.departamento} onChange={e => { f('departamento', e.target.value); f('ciudad', ''); fetchCities(e.target.value); }}>
                    <option value="">— Seleccionar —</option>
                    {departments.map(d => <option key={d} value={d}>{d}</option>)}
                  </select>
                </div>
                <div>
                  <label>Ciudad / Municipio</label>
                  <select value={editForm.ciudad} onChange={e => f('ciudad', e.target.value)} disabled={!editForm.departamento}>
                    <option value="">— Seleccionar —</option>
                    {cities.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div style={{ gridColumn: '1 / -1' }}>
                  <label>Dirección</label>
                  <input value={editForm.direccion} onChange={e => f('direccion', e.target.value)} placeholder="Cra 100 # 20 - 30" />
                </div>
                <div>
                  <label>Zona Geográfica</label>
                  <input value={editForm.zona_geografica} onChange={e => f('zona_geografica', e.target.value)} placeholder="Ej: Norte, Sur, Centro" />
                </div>
                <div>
                  <label>Categoría</label>
                  <select value={editForm.categoria} onChange={e => f('categoria', e.target.value)}>
                    <option value="">— Sin categoría —</option>
                    <option value="A">A</option>
                    <option value="B">B</option>
                    <option value="C">C</option>
                  </select>
                </div>
                <div>
                  <label>Fecha de Vinculación</label>
                  <input type="date" value={editForm.fecha_vinculacion} onChange={e => f('fecha_vinculacion', e.target.value)} />
                </div>
                <div>
                  <label>Estado en la Red</label>
                  <select value={editForm.estado_red} onChange={e => f('estado_red', e.target.value)}>
                    <option value="activo">Activo</option>
                    <option value="suspendido">Suspendido</option>
                    <option value="retirado">Retirado</option>
                  </select>
                </div>

                {/* Campos de taller — solo si has_service */}
                {editForm.has_service && (
                  <>
                    <div style={{ gridColumn: '1 / -1', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 14, marginTop: 4 }}>
                      <p style={{ fontSize: 9, fontWeight: 800, color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', letterSpacing: '0.07em', margin: 0 }}>Datos de taller</p>
                    </div>
                    <div>
                      <label>Capacidad de Bahías</label>
                      <input type="number" min="0" value={editForm.capacidad_bahias} onChange={e => f('capacidad_bahias', e.target.value)} placeholder="Ej: 4" />
                    </div>
                    <div>
                      <label>Número de Técnicos</label>
                      <input type="number" min="0" value={editForm.numero_tecnicos} onChange={e => f('numero_tecnicos', e.target.value)} placeholder="Ej: 3" />
                    </div>
                    <div>
                      <label>Tipo de Servicio</label>
                      <select value={editForm.tipo_servicio} onChange={e => f('tipo_servicio', e.target.value)}>
                        <option value="Todos">Todos</option>
                        <option value="Revisiones/Express">Revisiones / Express</option>
                      </select>
                    </div>
                  </>
                )}
              </div>
            </div>

            <div className="modal-foot">
              <button onClick={() => setShowModal(false)} className="btn-secondary">Cancelar</button>
              <button onClick={saveTenant} disabled={saving || !editForm.name} className="btn-primary">
                <Save size={14} /> {saving ? 'Guardando...' : 'Guardar'}
              </button>
            </div>
          </div>
        </div>
      )}

      <style jsx>{`
        .tenants-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1.25rem; }
        .tenant-card { background: #111114; border: 1px solid rgba(255,255,255,0.05); border-radius: 16px; overflow: hidden; transition: all 0.25s; }
        .tenant-card:hover { transform: translateY(-3px); border-color: rgba(251,146,60,0.25); box-shadow: 0 10px 24px -8px rgba(0,0,0,0.5), 0 0 24px -8px rgba(251,146,60,0.12); }
        .edit-btn { width: 30px; height: 30px; border-radius: 8px; background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.4); display: flex; align-items: center; justify-content: center; border: 1px solid rgba(255,255,255,0.08); cursor: pointer; transition: all 0.2s; flex-shrink: 0; }
        .edit-btn:hover { background: #fb923c; color: white; border-color: #fb923c; }
        .btn-primary { display: flex; align-items: center; gap: 6px; background: #ff5f33; color: white; border: none; padding: 0.65rem 1.1rem; border-radius: 9px; font-weight: 800; text-transform: uppercase; font-size: 11px; cursor: pointer; transition: all 0.2s; }
        .btn-primary:hover:not(:disabled) { background: #e04a22; }
        .btn-primary:disabled { opacity: 0.5; cursor: default; }
        .btn-secondary { background: transparent; border: 1px solid rgba(255,255,255,0.15); color: white; padding: 0.65rem 1.1rem; border-radius: 9px; font-weight: 800; font-size: 11px; text-transform: uppercase; cursor: pointer; }
        .modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.8); backdrop-filter: blur(4px); z-index: 1000; display: flex; align-items: center; justify-content: center; padding: 1.5rem; }
        .modal-box { background: #0c0c0e; border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; width: 100%; box-shadow: 0 25px 50px rgba(0,0,0,0.8); overflow: hidden; }
        .modal-head { display: flex; justify-content: space-between; align-items: center; padding: 1.25rem 1.5rem; border-bottom: 1px solid rgba(255,255,255,0.05); background: rgba(255,255,255,0.02); }
        .close-btn { width: 26px; height: 26px; border-radius: 7px; background: rgba(255,255,255,0.08); border: none; color: white; display: flex; justify-content: center; align-items: center; cursor: pointer; }
        .close-btn:hover { background: #ef4444; }
        .modal-body { padding: 1.5rem; }
        .modal-body label { display: block; font-size: 9px; font-weight: 800; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 5px; }
        .modal-body input, .modal-body select { width: 100%; background: #151518; border: 1px solid rgba(255,255,255,0.08); padding: 0.65rem 0.9rem; border-radius: 8px; color: white; font-size: 12px; outline: none; box-sizing: border-box; }
        .modal-body input:focus, .modal-body select:focus { border-color: #fb923c; }
        .modal-foot { display: flex; justify-content: flex-end; gap: 10px; padding: 1.25rem 1.5rem; border-top: 1px solid rgba(255,255,255,0.05); background: rgba(0,0,0,0.2); }
      `}</style>
    </AdminLayout>
  );
}
