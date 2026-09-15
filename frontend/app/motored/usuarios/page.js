'use client';
/**
 * frontend/app/motored/usuarios/page.js
 *
 * ADMIN-only usuario list/create/deactivate (sdd/motored-pedidos-cimientos,
 * Phase 6, task 6.2). Backend already enforces ADMIN-only server-side
 * (`backend/app/motored/api/usuarios.py`'s `_require_admin`) -- this screen
 * additionally hides itself from the menu for non-ADMIN roles
 * (`MotoredSidebar`'s `adminOnly` filter) and redirects a non-ADMIN who
 * navigates here directly straight back to `/motored/maestros`, mirroring
 * asc360's `admin-layout.js` division of labor (UI convenience gate, real
 * enforcement is server-side).
 */
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import MotoredLayout from '../motored-layout';
import { listUsuarios, createUsuario, deactivateUsuario } from '../../../lib/motored/api';
import { MOTORED_USER_KEY } from '../../../lib/motored/motoredFetch';

const ROLES = ['ADMIN', 'COMPRAS', 'SUCURSAL', 'CONSULTA'];
const emptyForm = { nombre: '', email: '', password: '', role: 'CONSULTA' };

function UsuarioForm({ form, setForm, onSubmit }) {
  return (
    <form onSubmit={onSubmit} style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Nombre
        <input value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} required />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Email
        <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Password
        <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Rol
        <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
          {ROLES.map((r) => (
            <option key={r} value={r} style={{ color: '#1a1a18' }}>
              {r}
            </option>
          ))}
        </select>
      </label>
      <button type="submit" className="motored-btn motored-btn-primary">Crear usuario</button>
    </form>
  );
}

function UsuariosTable({ usuarios, onDeactivate }) {
  const handleDeactivateClick = (u) => {
    if (window.confirm(`¿Desactivar a "${u.nombre}"? No se elimina, queda marcado como inactivo.`)) {
      onDeactivate(u.id);
    }
  };

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
      <thead>
        <tr style={{ textAlign: 'left', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          <th style={{ padding: '0 12px 8px 0' }}>Nombre</th>
          <th style={{ padding: '0 12px 8px 0' }}>Email</th>
          <th style={{ padding: '0 12px 8px 0' }}>Rol</th>
          <th style={{ padding: '0 12px 8px 0' }}>Estado</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {usuarios.map((u) => (
          <tr key={u.id} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
            <td style={{ padding: '10px 12px 10px 0' }}>{u.nombre}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{u.email}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{u.role}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{u.activo ? 'Activo' : 'Inactivo'}</td>
            <td style={{ padding: '10px 0' }}>
              {/* Nunca un botón rojo dentro de una tabla -- ver
              SucursalesTab.js para la misma regla aplicada. */}
              {u.activo && (
                <button type="button" className="motored-row-action" onClick={() => handleDeactivateClick(u)}>Desactivar</button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function useAdminGate() {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    const stored = sessionStorage.getItem(MOTORED_USER_KEY);
    let role = null;
    try {
      role = stored ? JSON.parse(stored).role : null;
    } catch {
      role = null;
    }
    if (role !== 'ADMIN') {
      router.push('/motored/maestros');
      return;
    }
    setAllowed(true);
  }, [router]);

  return allowed;
}

function useUsuarios(enabled) {
  const [usuarios, setUsuarios] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await listUsuarios();
      setUsuarios(data);
    } catch (err) {
      setError(err.message || 'Error al cargar usuarios');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (enabled) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  const create = async (form) => {
    setError('');
    try {
      await createUsuario(form);
      await load();
      return true;
    } catch (err) {
      setError(err.message || 'Error al crear usuario');
      return false;
    }
  };

  const deactivate = async (id) => {
    setError('');
    try {
      await deactivateUsuario(id);
      await load();
    } catch (err) {
      setError(err.message || 'Error al desactivar usuario');
    }
  };

  return { usuarios, loading, error, create, deactivate };
}

function UsuariosContent() {
  const allowed = useAdminGate();
  const { usuarios, loading, error, create, deactivate } = useUsuarios(allowed);
  const [form, setForm] = useState(emptyForm);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const ok = await create(form);
    if (ok) setForm(emptyForm);
  };

  if (!allowed) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <h2 className="motored-h-seccion">Usuarios</h2>

      {error && <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{error}</p>}

      <UsuarioForm form={form} setForm={setForm} onSubmit={handleSubmit} />

      {loading ? (
        <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>Cargando...</p>
      ) : (
        <UsuariosTable usuarios={usuarios} onDeactivate={deactivate} />
      )}
    </div>
  );
}

export default function UsuariosPage() {
  return (
    <MotoredLayout>
      <UsuariosContent />
    </MotoredLayout>
  );
}
