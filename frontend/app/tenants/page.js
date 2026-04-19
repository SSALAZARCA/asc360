'use client';
import { useState, useEffect } from 'react';
import AdminLayout from '../admin-layout';
import { Building2, Edit, Save, X, Phone, MapPin, Hash, Plus, CheckCircle, XCircle } from 'lucide-react';
import { authFetch } from '../../lib/authFetch';

const API = () => (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace(/^http:\/\/(?!localhost)/, 'https://');

export default function TenantsPage() {
  const [tenants, setTenants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editForm, setEditForm] = useState(null);
  const [departments, setDepartments] = useState([]);
  const [cities, setCities] = useState([]);

  const fetchTenants = async () => {
    try {
      const response = await authFetch('/tenants');
      const data = await response.json();
      setTenants(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error("Error", e);
    } finally {
      setLoading(false);
    }
  };

  const fetchDepartments = async () => {
    try {
      const res = await fetch(`${API()}/tenants/divipola/departments`);
      const data = await res.json();
      setDepartments(data);
    } catch (e) {
      console.error('Error cargando departamentos', e);
    }
  };

  const fetchCities = async (departamento) => {
    if (!departamento) { setCities([]); return; }
    try {
      const res = await fetch(`${API()}/tenants/divipola/cities?departamento=${encodeURIComponent(departamento)}`);
      const data = await res.json();
      setCities(data);
    } catch (e) {
      console.error('Error cargando ciudades', e);
    }
  };

  useEffect(() => { fetchTenants(); fetchDepartments(); }, []);

  const openNew = () => {
    setCities([]);
    setEditForm({ name: '', tenant_type: 'workshop', nit: '', phone: '', address: '', ciudad: '', departamento: '', status: 'active' });
    setShowModal(true);
  };

  const openEdit = (t) => {
    if (t.departamento) fetchCities(t.departamento);
    else setCities([]);
    setEditForm(t);
    setShowModal(true);
  };

  const handleDepartamentoChange = (value) => {
    setEditForm(f => ({ ...f, departamento: value, ciudad: '' }));
    fetchCities(value);
  };

  const saveTenant = async () => {
    try {
      const method = editForm.id ? 'PUT' : 'POST';
      const url = editForm.id ? `/tenants/${editForm.id}` : '/tenants';
      
      const res = await authFetch(url, {
        method,
        body: JSON.stringify(editForm)
      });
      
      if (res.ok) {
        setShowModal(false);
        fetchTenants();
      } else {
        alert("Error al guardar en el servidor");
      }
    } catch (e) {
      alert("Error de conexión");
    }
  };

  return (
    <AdminLayout>
      <header className="page-header mb-8 flex justify-between items-end border-b border-white/5 pb-6">
        <div>
          <h1 className="page-title">Red de Talleres</h1>
          <p className="text-muted text-sm tracking-wide mt-1">Administración logística de la red nacional UM Colombia</p>
        </div>
        <button className="btn-primary" onClick={openNew}>
          <Plus size={16} /> Agregar Taller
        </button>
      </header>

      <div className="tenants-grid">
        {loading ? (
             <div className="glass p-12 text-center col-span-full text-white/50 animate-pulse">Consultando base de datos nacional...</div>
        ) : tenants.map(t => (
          <div key={t.id} className="tenant-card relative group">
            <div className={`status-bar ${t.status === 'inactive' ? 'bg-red-500' : 'bg-green-500'}`}></div>
            <div className="p-6">
              <div className="flex justify-between items-start">
                <div className="flex items-center gap-4">
                   <div className="w-12 h-12 rounded-xl bg-orange-500/10 flex items-center justify-center border border-orange-500/20">
                      <Building2 size={22} className="text-orange-500" />
                   </div>
                   <div>
                      <h3 className="font-black text-lg text-white leading-tight uppercase tracking-tight">{t.name}</h3>
                      <div className="flex gap-2 items-center mt-1">
                        <span className="text-[10px] bg-white/10 px-2 py-0.5 rounded text-white/70 uppercase font-bold tracking-wider">{t.tenant_type}</span>
                        {t.status === 'inactive' && <span className="text-[10px] bg-red-500/20 px-2 py-0.5 rounded text-red-400 font-bold uppercase flex items-center gap-1"><XCircle size={10}/> Inactivo</span>}
                      </div>
                   </div>
                </div>
                <button onClick={() => openEdit(t)} className="edit-btn">
                   <Edit size={16} />
                </button>
              </div>

              <div className="details mt-6 space-y-3">
                 <div className="flex items-center gap-3 text-sm text-white/70">
                    <Hash size={14} className="text-white/30" />
                    <span className="font-mono">{t.nit || 'Sin NIT registrado'}</span>
                 </div>
                 <div className="flex items-center gap-3 text-sm text-white/70">
                    <MapPin size={14} className="text-white/30" />
                    <span className="truncate">{t.ciudad || 'Global'}, {t.departamento}</span>
                 </div>
                 <div className="flex items-center gap-3 text-sm text-white/70">
                    <Phone size={14} className="text-white/30" />
                    <span className="font-mono">{t.phone || 'Sin número'}</span>
                 </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {showModal && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <div className="modal-head">
              <h2 className="text-lg font-black uppercase text-white tracking-tight">{editForm.id ? 'Editar Taller' : 'Nuevo Taller'}</h2>
              <button onClick={() => setShowModal(false)} className="close-btn"><X size={16}/></button>
            </div>
            <div className="modal-body">
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label>Razón Social / Nombre</label>
                  <input value={editForm.name} onChange={e => setEditForm({...editForm, name: e.target.value})} placeholder="Ej: Motors 100 S.A.S" />
                </div>
                <div>
                  <label>NIT</label>
                  <input value={editForm.nit} onChange={e => setEditForm({...editForm, nit: e.target.value})} placeholder="Ej: 900.123.456-1" />
                </div>
                <div>
                  <label>Teléfono Contacto</label>
                  <input value={editForm.phone} onChange={e => setEditForm({...editForm, phone: e.target.value})} placeholder="Ej: 300 123 4567" />
                </div>
                <div>
                  <label>Departamento</label>
                  <select value={editForm.departamento} onChange={e => handleDepartamentoChange(e.target.value)}>
                    <option value="">— Seleccionar —</option>
                    {departments.map(d => <option key={d} value={d}>{d}</option>)}
                  </select>
                </div>
                <div>
                  <label>Ciudad / Municipio</label>
                  <select value={editForm.ciudad} onChange={e => setEditForm({...editForm, ciudad: e.target.value})} disabled={!editForm.departamento}>
                    <option value="">— Seleccionar —</option>
                    {cities.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div className="col-span-2">
                  <label>Dirección Física</label>
                  <input value={editForm.address} onChange={e => setEditForm({...editForm, address: e.target.value})} placeholder="Ej: Cra 100 # 20 - 30" />
                </div>
                <div>
                  <label>Tipo de Centro</label>
                  <select value={editForm.tenant_type} onChange={e => setEditForm({...editForm, tenant_type: e.target.value})}>
                    <option value="workshop">Taller Autorizado</option>
                    <option value="dealer">Distribuidor</option>
                    <option value="admin">Sede Principal Administrativa</option>
                  </select>
                </div>
                <div>
                  <label>Estado Operativo</label>
                  <select value={editForm.status} onChange={e => setEditForm({...editForm, status: e.target.value})}>
                    <option value="active">Activo (Operando)</option>
                    <option value="inactive">Inactivo (Suspendido)</option>
                  </select>
                </div>
              </div>
            </div>
            <div className="modal-foot">
              <button onClick={() => setShowModal(false)} className="btn-secondary">Cancelar</button>
              <button onClick={saveTenant} className="btn-primary"><Save size={16}/> Guardar Taller</button>
            </div>
          </div>
        </div>
      )}

      <style jsx>{`
        .tenants-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
          gap: 1.5rem;
        }

        .tenant-card {
          background: #111114;
          border: 1px solid rgba(255,255,255,0.05);
          border-radius: 16px;
          overflow: hidden;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .tenant-card:hover {
          transform: translateY(-4px);
          border-color: rgba(255, 95, 51, 0.3);
          box-shadow: 0 12px 24px -10px rgba(0,0,0,0.5), 0 0 30px -10px rgba(255, 95, 51, 0.15);
        }

        .status-bar { height: 4px; width: 100%; top: 0; left: 0; position: absolute; }
        
        .edit-btn {
          width: 32px; height: 32px;
          border-radius: 10px;
          background: rgba(255,255,255,0.05);
          color: rgba(255,255,255,0.5);
          display: flex; align-items: center; justify-content: center;
          border: 1px solid rgba(255,255,255,0.1);
          cursor: pointer; transition: all 0.2s;
        }
        .edit-btn:hover { background: var(--accent-primary); color: white; border-color: var(--accent-primary); }

        .btn-primary { 
          display: flex; align-items: center; gap: 0.5rem;
          background: #ff5f33; color: white; border: none; 
          padding: 0.75rem 1.25rem; border-radius: 10px; font-weight: 800; text-transform: uppercase; font-size: 0.75rem; tracking: wide;
          cursor: pointer; box-shadow: 0 4px 15px rgba(255, 95, 51, 0.3); transition: all 0.2s; 
        }
        .btn-primary:hover { background: #e04a22; transform: translateY(-2px); box-shadow: 0 6px 20px rgba(255, 95, 51, 0.4); }
        
        .btn-secondary {
          background: transparent; border: 1px solid rgba(255,255,255,0.2); color: white;
          padding: 0.75rem 1.25rem; border-radius: 10px; font-weight: 800; font-size: 0.75rem; text-transform: uppercase;
          cursor: pointer; transition: all 0.2s;
        }
        .btn-secondary:hover { background: rgba(255,255,255,0.1); }

        /* Modal Styles */
        .modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.8); backdrop-filter: blur(4px); z-index: 1000; display: flex; align-items: center; justify-content: center; padding: 2rem; }
        .modal-box { background: #0c0c0e; border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; width: 100%; max-width: 600px; box-shadow: 0 25px 50px rgba(0,0,0,0.8); overflow: hidden; }
        .modal-head { display: flex; justify-content: space-between; align-items: center; padding: 1.5rem; border-bottom: 1px solid rgba(255,255,255,0.05); background: rgba(255,255,255,0.02); }
        .close-btn { width: 28px; height: 28px; border-radius: 8px; background: rgba(255,255,255,0.1); border: none; color: white; display: flex; justify-content: center; align-items: center; cursor: pointer; }
        .close-btn:hover { background: #ef4444; }
        
        .modal-body { padding: 1.5rem; }
        .modal-body label { display: block; font-size: 0.65rem; font-weight: 800; color: rgba(255,255,255,0.5); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.4rem; }
        .modal-body input, .modal-body select { width: 100%; background: #151518; border: 1px solid rgba(255,255,255,0.1); padding: 0.75rem 1rem; border-radius: 10px; color: white; font-size: 0.85rem; outline: none; transition: border-color 0.2s; }
        .modal-body input:focus, .modal-body select:focus { border-color: #ff5f33; }
        
        .modal-foot { display: flex; justify-content: flex-end; gap: 1rem; padding: 1.5rem; border-top: 1px solid rgba(255,255,255,0.05); background: rgba(0,0,0,0.2); }
      `}</style>
    </AdminLayout>
  );
}
