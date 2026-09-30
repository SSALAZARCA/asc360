'use client';
/** Password input with its own show/hide toggle and a label tied to the input. */
import { useState, useId } from 'react';
import { Eye, EyeOff } from 'lucide-react';

const wrapStyle = { display: 'flex', flexDirection: 'column', gap: '0.35rem' };
const rowStyle = { position: 'relative', display: 'flex', alignItems: 'center' };
const labelStyle = { fontSize: '0.75rem', fontWeight: 700, color: 'var(--motored-text-muted, #5a5a5a)' };
const toggleStyle = {
  position: 'absolute', right: '0.4rem', background: 'transparent', border: 'none', cursor: 'pointer',
  color: 'var(--motored-text-muted, #5a5a5a)', minWidth: '44px', minHeight: '44px',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
};
const hintStyle = { margin: 0, fontSize: '0.7rem', color: 'var(--motored-text-soft, #8a8a8a)' };

export default function PasswordField({ label, value, onChange, autoComplete, hint, maxLength = 72 }) {
  const id = useId();
  const [visible, setVisible] = useState(false);
  const Icon = visible ? EyeOff : Eye;
  return (
    <div style={wrapStyle}>
      <label htmlFor={id} style={labelStyle}>{label}</label>
      <div style={rowStyle}>
        <input
          id={id} type={visible ? 'text' : 'password'} value={value} autoComplete={autoComplete}
          maxLength={maxLength} required onChange={(e) => onChange(e.target.value)}
          style={{ width: '100%', paddingRight: '3rem', minHeight: '44px' }}
        />
        <button
          type="button" style={toggleStyle} onClick={() => setVisible((v) => !v)}
          aria-label={`${visible ? 'Ocultar' : 'Mostrar'} ${label}`}
        >
          <Icon size={16} />
        </button>
      </div>
      {hint && <p style={hintStyle}>{hint}</p>}
    </div>
  );
}
