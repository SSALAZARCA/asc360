'use client';
/**
 * Create-user form for the Usuarios screen. The password must be typed twice
 * and match before anything is sent; the confirmation never leaves this form.
 */
import { useState } from 'react';
import PasswordField from './mi-cuenta/PasswordField';
import { PASSWORD_MIN_LENGTH } from './CambiarPasswordForm';

const ROLES = ['ADMIN', 'COMPRAS', 'SUCURSAL', 'CONSULTA', 'SERVICIO_CLIENTE'];
const ROLE_LABELS = { SERVICIO_CLIENTE: 'Servicio al cliente' };
const EMPTY_FORM = { nombre: '', email: '', password: '', role: 'CONSULTA' };

const labelStyle = { display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' };
const rowStyle = { display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' };

// Same look as the plain Nombre/Email fields next to them.
const fieldStyles = {
  wrap: { gap: 0 },
  label: { fontSize: '0.7rem', fontWeight: 400 },
  input: { minHeight: 'auto' },
  toggle: { minHeight: '100%', minWidth: '36px' },
};

function validar(password, confirmacion) {
  if (password.length < PASSWORD_MIN_LENGTH) return `La contraseña debe tener al menos ${PASSWORD_MIN_LENGTH} caracteres`;
  if (password !== confirmacion) return 'Las contraseñas no coinciden';
  return '';
}

function IdentityFields({ form, setField }) {
  return (
    <>
      <label style={labelStyle}>
        Nombre
        <input value={form.nombre} onChange={(e) => setField('nombre', e.target.value)} required />
      </label>
      <label style={labelStyle}>
        Email
        <input type="email" autoComplete="off" value={form.email} onChange={(e) => setField('email', e.target.value)} required />
      </label>
    </>
  );
}

function RoleSelect({ value, onChange }) {
  return (
    <label style={labelStyle}>
      Rol
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {ROLES.map((r) => (
          <option key={r} value={r} style={{ color: '#1a1a18' }}>
            {ROLE_LABELS[r] || r}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function UsuarioCreateForm({ onCreate }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [confirmacion, setConfirmacion] = useState('');
  const [error, setError] = useState('');
  const setField = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    const problema = validar(form.password, confirmacion);
    setError(problema);
    if (problema) return;
    if (await onCreate(form)) {
      setForm(EMPTY_FORM);
      setConfirmacion('');
    }
  };

  return (
    <form onSubmit={handleSubmit} style={rowStyle}>
      <IdentityFields form={form} setField={setField} />
      <PasswordField
        label="Contraseña" value={form.password} onChange={(v) => setField('password', v)}
        autoComplete="new-password" toggleName="contraseña" styles={fieldStyles}
      />
      <PasswordField
        label="Confirmar contraseña del usuario" value={confirmacion} onChange={setConfirmacion}
        autoComplete="new-password" toggleName="confirmación de contraseña" styles={fieldStyles}
      />
      <RoleSelect value={form.role} onChange={(v) => setField('role', v)} />
      <button type="submit" className="motored-btn motored-btn-primary">Crear usuario</button>
      <p style={{ margin: 0, width: '100%', fontSize: '0.7rem', color: 'var(--motored-text-soft, #8a8a8a)' }}>
        Mínimo {PASSWORD_MIN_LENGTH} caracteres (máximo 72).
      </p>
      {error && <p role="alert" style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem', width: '100%', margin: 0 }}>{error}</p>}
    </form>
  );
}
