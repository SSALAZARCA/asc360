'use client';
/**
 * frontend/components/motored/MotoredIconAction.js
 *
 * Icon-only row action with a hover/focus label. The accessible name is the
 * action word (aria-label), the tooltip is state-driven (mouse and keyboard
 * focus, which also fires on tap) and styled inline, so nothing depends on
 * the shared themeCss. `touch` raises the target to 44 px for tablet rows.
 */
import { useState } from 'react';
import { ACTION_ICONS } from './actionIcons';

const BTN = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  minWidth: '32px', minHeight: '32px', background: 'transparent',
  border: 'none', borderRadius: '6px', cursor: 'pointer', padding: 0,
};
const BTN_TOUCH = { minWidth: '44px', minHeight: '44px' };
const TIP = {
  position: 'absolute', bottom: '105%', left: '50%', transform: 'translateX(-50%)',
  background: 'var(--motored-text, #1a1a18)', color: '#fff', padding: '4px 8px',
  borderRadius: '4px', fontSize: '11px', fontWeight: 500, whiteSpace: 'nowrap',
  pointerEvents: 'none', zIndex: 20,
};

export default function MotoredIconAction({ action, label, onClick, variant = 'default', disabled = false, touch = false }) {
  const [visible, setVisible] = useState(false);
  const text = label || action;
  const Icon = ACTION_ICONS[action];
  const color = variant === 'danger' ? 'var(--motored-danger, #c0392b)' : 'var(--motored-text-muted, #5a5a5a)';
  return (
    <span style={{ position: 'relative', display: 'inline-flex' }}>
      <button
        type="button" aria-label={text} data-variant={variant}
        style={{ ...BTN, ...(touch ? BTN_TOUCH : {}), color, opacity: disabled ? 0.5 : 1, cursor: disabled ? 'not-allowed' : 'pointer' }}
        onClick={onClick} disabled={disabled}
        onMouseEnter={() => setVisible(true)} onMouseLeave={() => setVisible(false)}
        onFocus={() => setVisible(true)} onBlur={() => setVisible(false)}
      >
        {Icon && <Icon size={16} aria-hidden="true" />}
      </button>
      {visible && <span role="tooltip" style={TIP}>{text}</span>}
    </span>
  );
}
