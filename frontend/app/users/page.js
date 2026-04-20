'use client';
import { useState, useEffect } from 'react';
import AdminLayout from '../admin-layout';
import { UserCheck, UserX, Shield, Briefcase, Mail, Phone, Send, Plus, Users as UsersIcon, Edit, X, Trash2 } from 'lucide-react';
import { authFetch } from '../../lib/authFetch';

export default function UsersPage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editForm, setEditForm] = useState(null);
  const [currentUserId, setCurrentUserId] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);

  useEffect(() => {
    const stored = sessionStorage.getItem('um_user');
    if (stored) setCurrentUserId(JSON.parse(stored).id);
  }, []);

  const fetchUsers = async () => {
    try {
      const response = await authFetch('/users');
      const data = await response.json();
      setUsers(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error("Error", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchUsers(); }, []);

  const deleteUser = async () => {
    if (!confirmDelete) return;
    try {
      const res = await authFetch(`/users/${confirmDelete.id}`, { method: 'DELETE' });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        alert(body.detail || `Error ${res.status} al eliminar`);
        return;
      }
      setConfirmDelete(null);
      await fetchUsers();
    } catch (e) {
      alert('Error de conexión al eliminar');
    }
  };

  const updateStatus = async (userId, newStatus) => {
    try {
      await authFetch(`/users/${userId}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status: newStatus })
      });
      fetchUsers();
    } catch (e) {
      alert("Error al actualizar");
    }
  };

  const openNew = () => {
    setEditForm({ name: '', role: 'technician', email: '', phone: '', status: 'active', telegram_id: '', password: '' });
    setShowModal(true);
  };

  const openEdit = (u) => {
    setEditForm({ ...u, password: '' });
    setShowModal(true);
  };

  const saveUser = async () => {
    try {
      if (editForm.id) {
        await authFetch(`/users/${editForm.id}`, {
          method: 'PATCH',
          body: JSON.stringify({
            name: editForm.name,
            email: editForm.email,
            phone: editForm.phone,
            role: editForm.role,
            telegram_id: editForm.telegram_id || null,
          })
        });
        if (editForm.password) {
          await authFetch(`/users/${editForm.id}/password`, {
            method: 'PATCH',
            body: JSON.stringify({ password: editForm.password })
          });
        }
      } else {
        await authFetch('/users', {
          method: 'POST',
          body: JSON.stringify({
            name: editForm.name,
            email: editForm.email,
            phone: editForm.phone,
            role: editForm.role,
            telegram_id: editForm.telegram_id || null,
            status: 'active',
            password: editForm.password || null,
          })
        });
      }
      setShowModal(false);
      fetchUsers();
    } catch (e) {
      console.error(e);
      alert('Error al guardar el usuario');
    }
  };

  return (
    <AdminLayout>
      <header className="page-header mb-8 flex justify-between items-end border-b border-white/5 pb-6">
        <div>
          <h1 className="page-title">Personal y <span style={{ fontStyle: 'italic', color: 'var(--accent-orange)', WebkitTextFillColor: 'var(--accent-orange)' }}>Acceso</span></h1>
          <p className="text-muted text-sm tracking-wide mt-1">Gestión de identidad, roles de seguridad y acceso web/telegram</p>
        </div>
        <button className="btn-primary" onClick={openNew}>
          <Plus size={16} /> Invitar Personal
        </button>
      </header>

      <div className="glass overflow-hidden rounded-2xl border border-white/5 shadow-2xl">
        <table className="master-table">
          <thead>
            <tr>
              <th>Nombre Completo</th>
              <th>Rol Asignado</th>
              <th>Contactos (Web/Bot)</th>
              <th>Taller Asignado</th>
              <th>Estado Acceso</th>
              <th className="text-right">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="6" className="text-center py-20 text-white/50 animate-pulse font-bold uppercase tracking-wider text-sm">Validando biometría y accesos...</td></tr>
            ) : users.map((u) => (
              <tr key={u.id} className="hover:bg-white/5 transition-colors border-b border-white/5">
                <td className="py-4">
                  <div className="flex items-center gap-4">
                    <div className="avatar-small">{u.name.substring(0,2).toUpperCase()}</div>
                    <span className="font-bold text-white tracking-tight">{u.name}</span>
                  </div>
                </td>
                <td>
                  <span className={`role-badge ${u.role}`}>
                    {u.role === 'superadmin' ? <Shield size={12} /> : <Briefcase size={12} />}
                    {u.role}
                  </span>
                </td>
                <td>
                  <div className="flex flex-col gap-1 text-[11px] text-white/60 font-mono">
                    <span className="flex items-center gap-1.5"><Mail size={12} className="text-white/30" /> {u.email || 'N/A'}</span>
                    <span className="flex items-center gap-1.5"><Phone size={12} className="text-white/30" /> {u.phone || 'N/A'}</span>
                    <span className="flex items-center gap-1.5 text-blue-400/80"><Send size={12} /> {u.telegram_id ? 'Vinculado' : 'Pendiente Telegram'}</span>
                  </div>
                </td>
                <td>
                  <span className="px-2 py-1 bg-white/5 rounded-md text-xs font-bold text-white/70 uppercase tracking-tighter border border-white/5">
                    {u.service_center_name || (u.tenant?.name) || 'ACCESO GLOBAL'}
                  </span>
                </td>
                <td>
                  <div className="flex items-center gap-2">
                    <span className={`status-point ${u.status}`}></span>
                    <span className="text-[10px] uppercase font-black tracking-widest text-white/80">
                      {u.status === 'active' ? 'HABILITADO' : u.status === 'pending' ? 'PENDIENTE' : 'RECHAZADO'}
                    </span>
                  </div>
                </td>
                <td className="text-right">
                  <div className="flex justify-end gap-1.5">
                    <button onClick={() => openEdit(u)} className="action-btn text-white/50 hover:text-white bg-white/5 hover:bg-white/10" title="Editar Perfil">
                      <Edit size={14} />
                    </button>
                    {u.status === 'pending' && (
                      <button onClick={() => updateStatus(u.id, 'active')} className="action-btn text-green-500 bg-green-500/10 hover:bg-green-500/20" title="Aprobar Acceso">
                        <UserCheck size={14} />
                      </button>
                    )}
                    {(u.status === 'active' || u.status === 'pending') && (
                      <button onClick={() => updateStatus(u.id, 'rejected')} className="action-btn text-red-500 bg-red-500/10 hover:bg-red-500/20" title="Revocar Acceso">
                        <UserX size={14} />
                      </button>
                    )}
                    {u.id !== currentUserId && (
                      <button onClick={() => setConfirmDelete({ id: u.id, name: u.name })} className="action-btn text-red-700 bg-red-900/20 hover:bg-red-900/40" title="Eliminar Usuario">
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showModal && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <div className="modal-head">
              <h2 className="text-lg font-black uppercase text-white tracking-tight">{editForm.id ? 'Editar Personal' : 'Invitar Personal'}</h2>
              <button onClick={() => setShowModal(false)} className="close-btn"><X size={16}/></button>
            </div>
            <div className="modal-body">
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label>Nombre Completo</label>
                  <input value={editForm.name} onChange={e => setEditForm({...editForm, name: e.target.value})} placeholder="Ej: Carlos Técnico" />
                </div>
                <div>
                  <label>Rol del Sistema</label>
                  <select value={editForm.role} onChange={e => setEditForm({...editForm, role: e.target.value})}>
                    <option value="technician">Técnico Mecánico</option>
                    <option value="jefe_taller">Jefe / Coordinador de Taller</option>
                    <option value="administrativo">Administrativo</option>
                    <option value="superadmin">Super Admin (Global)</option>
                  </select>
                </div>
                <div>
                  <label>Cédula / Telegram ID</label>
                  <input value={editForm.telegram_id} onChange={e => setEditForm({...editForm, telegram_id: e.target.value})} placeholder="Opcional. Para acceso al bot" />
                </div>
                <div>
                  <label>Correo de Acceso Panel Web</label>
                  <input value={editForm.email} onChange={e => setEditForm({...editForm, email: e.target.value})} type="email" placeholder="carlos@taller.com" />
                </div>
                <div>
                  <label>Teléfono Móvil</label>
                  <input value={editForm.phone} onChange={e => setEditForm({...editForm, phone: e.target.value})} placeholder="+57 300 000 0000" />
                </div>
                <div className="col-span-2">
                  <label>{editForm.id ? 'Nueva Contraseña (dejar vacío para no cambiar)' : 'Contraseña de Acceso Web'}</label>
                  <input value={editForm.password} onChange={e => setEditForm({...editForm, password: e.target.value})} type="password" placeholder={editForm.id ? '••••••••' : 'Mínimo 8 caracteres'} />
                </div>
              </div>
            </div>
            <div className="modal-foot">
              <button onClick={() => setShowModal(false)} className="btn-secondary">Cancelar</button>
              <button onClick={saveUser} className="btn-primary">Generar Acceso</button>
            </div>
          </div>
        </div>
      )}

      {confirmDelete && (
        <div className="modal-backdrop">
          <div className="modal-box" style={{ maxWidth: '420px' }}>
            <div className="modal-head">
              <h2 className="text-lg font-black uppercase text-white tracking-tight">Eliminar Usuario</h2>
              <button onClick={() => setConfirmDelete(null)} className="close-btn"><X size={16}/></button>
            </div>
            <div className="modal-body">
              <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.85rem', lineHeight: '1.6' }}>
                Estás por eliminar a <span style={{ color: '#fff', fontWeight: 900 }}>{confirmDelete.name}</span>.<br/>
                Esta acción no se puede deshacer.
              </p>
            </div>
            <div className="modal-foot">
              <button onClick={() => setConfirmDelete(null)} className="btn-secondary">Cancelar</button>
              <button onClick={deleteUser} style={{ background: '#ef4444', color: '#fff', border: 'none', padding: '0.75rem 1.25rem', borderRadius: '10px', fontWeight: 900, fontSize: '0.75rem', textTransform: 'uppercase', cursor: 'pointer' }}>
                Eliminar
              </button>
            </div>
          </div>
        </div>
      )}

      <style jsx>{`
        .master-table { width: 100%; border-collapse: collapse; }
        .master-table th { text-align: left; padding: 1.25rem 1.5rem; color: rgba(255,255,255,0.4); font-weight: 800; border-bottom: 1px solid rgba(255,255,255,0.05); text-transform: uppercase; font-size: 0.65rem; letter-spacing: 0.05em; background: rgba(0,0,0,0.2); }
        .master-table td { padding: 1rem 1.5rem; }

        .avatar-small { width: 36px; height: 36px; border-radius: 12px; background: linear-gradient(135deg, rgba(255, 95, 51, 0.2), rgba(255, 95, 51, 0.05)); border: 1px solid rgba(255, 95, 51, 0.3); display: flex; align-items: center; justify-content: center; font-size: 0.8rem; font-weight: 900; color: #ff5f33; }
        
        .role-badge { display: inline-flex; align-items: center; gap: 0.4rem; padding: 4px 10px; border-radius: 8px; font-size: 0.65rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; }
        .superadmin { color: #f59e0b; background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); }
        .technician { color: #3b82f6; background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.3); }
        .jefe_taller { color: #10b981; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); }

        .status-point { display: inline-block; width: 6px; height: 6px; border-radius: 50%; }
        .active { background: #10b981; box-shadow: 0 0 10px #10b981; }
        .pending { background: #f59e0b; box-shadow: 0 0 10px #f59e0b; }
        .rejected, .inactive { background: #ef4444; box-shadow: 0 0 10px #ef4444; }

        .action-btn { width: 32px; height: 32px; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; border: none; cursor: pointer; transition: all 0.2s; }
        .action-btn:hover { transform: translateY(-2px); }

        .btn-primary { display: flex; align-items: center; gap: 0.5rem; background: #ff5f33; color: white; border: none; padding: 0.75rem 1.25rem; border-radius: 10px; font-weight: 800; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; cursor: pointer; box-shadow: 0 4px 15px rgba(255, 95, 51, 0.3); transition: all 0.2s; }
        .btn-primary:hover { background: #e04a22; transform: translateY(-2px); box-shadow: 0 6px 20px rgba(255, 95, 51, 0.4); }
        .btn-secondary { background: transparent; border: 1px solid rgba(255,255,255,0.2); color: white; padding: 0.75rem 1.25rem; border-radius: 10px; font-weight: 800; font-size: 0.75rem; text-transform: uppercase; cursor: pointer; transition: all 0.2s; }
        .btn-secondary:hover { background: rgba(255,255,255,0.1); }

        .modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.8); backdrop-filter: blur(4px); z-index: 1000; display: flex; align-items: center; justify-content: center; padding: 2rem; animation: fade 0.2s ease; }
        @keyframes fade { from { opacity: 0; } to { opacity: 1; } }
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
