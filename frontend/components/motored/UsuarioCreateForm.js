'use client';
/**
 * Create-user form for the Usuarios screen. The password must be typed twice
 * and match before anything is sent; the confirmation never leaves this form.
 * The optional cédula (odd/motored-reporte-diario-asesor, T1) is sent only
 * when filled; the backend validates it and stores it approved.
 */
import { useState } from 'react';
import PasswordField from './mi-cuenta/PasswordField';
import InfoTooltip from './InfoTooltip';
import { CEDULA_TOOLTIP } from './usuarios/CedulaUsuario';
import { PASSWORD_HINT, ADMIN_FORCED_CHANGE_NOTE, newPasswordProblem } from '../../lib/motored/passwordRules';

const ROLES = ['ADMIN', 'COMPRAS', 'SUCURSAL', 'CONSULTA', 'SERVICIO_CLIENTE', 'GERENCIA', 'COORDINADOR_REPUESTOS', 'LIDER_INVENTARIOS'];
const ROLE_LABELS = {
  SERVICIO_CLIENTE: 'Servicio al cliente', GERENCIA: 'Gerencia', COORDINADOR_REPUESTOS: 'Coordinador de repuestos',
  LIDER_INVENTARIOS: 'Líder de inventarios',
};
const EMPTY_FORM = {
  nombre: '', email: '', password: '', role: 'CONSULTA', cedula: '',
};

const labelStyle = { display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' };
const rowStyle = { display: 'flex', gap: '0.75rem', alignItems: 'flex-end', flexWrap: 'wrap' };

// Same look as the plain Nombre/Email fields next to them.
const fieldStyles = {
  wrap: { gap: 0 },
  label: { fontSize: '0.7rem', fontWeight: 400 },
  input: { minHeight: 'auto' },
  toggle: { minHeight: '100%', minWidth: '36px' },
};

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

function CedulaField({ value, onChange }) {
  return (
    <label style={labelStyle}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
        Cédula (opcional) <InfoTooltip text={CEDULA_TOOLTIP} />
      </span>
      <input
        aria-label="Cédula (opcional)" inputMode="numeric" autoComplete="off"
        value={value} onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

/** The cédula travels only when filled, so an empty one is never sent. */
function payloadDe(form) {
  const { cedula, ...resto } = form;
  const limpia = cedula.trim();
  return limpia ? { ...resto, cedula: limpia } : resto;
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
    const problema = newPasswordProblem(form.password, confirmacion);
    setError(problema);
    if (problema) return;
    if (await onCreate(payloadDe(form))) {
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
      <CedulaField value={form.cedula} onChange={(v) => setField('cedula', v)} />
      <button type="submit" className="motored-btn motored-btn-primary">Crear usuario</button>
      <p style={{ margin: 0, width: '100%', fontSize: '0.7rem', color: 'var(--motored-text-soft, #8a8a8a)' }}>
        {PASSWORD_HINT}
      </p>
      <p style={{ margin: 0, width: '100%', fontSize: '0.7rem', color: 'var(--motored-text-soft, #8a8a8a)' }}>
        {ADMIN_FORCED_CHANGE_NOTE}
      </p>
      {error && <p role="alert" style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem', width: '100%', margin: 0 }}>{error}</p>}
    </form>
  );
}
