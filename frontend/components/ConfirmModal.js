'use client';
import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle } from 'lucide-react';

export default function ConfirmModal({
  title,
  message,
  onConfirm,
  onCancel,
  danger = false,
  confirmLabel = 'Confirmar',
  cancelLabel = 'Cancelar',
}) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onCancel(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onCancel]);

  const accentColor = danger ? '#f97316' : '#3b82f6';
  const accentBg    = danger ? 'rgba(249,115,22,0.12)' : 'rgba(59,130,246,0.12)';
  const accentBorder = danger ? 'rgba(249,115,22,0.35)' : 'rgba(59,130,246,0.35)';

  return createPortal(
    <div
      onClick={onCancel}
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(0,0,0,0.72)', backdropFilter: 'blur(4px)',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#13131f',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: 12,
          padding: '1.5rem',
          width: '100%', maxWidth: 400,
          margin: '0 1rem',
          boxShadow: '0 24px 48px rgba(0,0,0,0.6)',
        }}
      >
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start', marginBottom: '1.25rem' }}>
          <div style={{
            flexShrink: 0, width: 36, height: 36, borderRadius: 8,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: accentBg,
          }}>
            <AlertTriangle size={18} color={accentColor} />
          </div>
          <div>
            {title && (
              <p style={{ margin: 0, marginBottom: 4, fontSize: '0.85rem', fontWeight: 700, color: '#f1f5f9' }}>
                {title}
              </p>
            )}
            <p style={{ margin: 0, fontSize: '0.78rem', color: 'rgba(255,255,255,0.6)', lineHeight: 1.6, whiteSpace: 'pre-line' }}>
              {message}
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
          <button
            onClick={onCancel}
            style={{
              padding: '0.45rem 1rem',
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 6, color: 'rgba(255,255,255,0.6)',
              fontSize: '0.75rem', fontWeight: 600, cursor: 'pointer',
            }}
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            style={{
              padding: '0.45rem 1rem',
              background: accentBg,
              border: `1px solid ${accentBorder}`,
              borderRadius: 6, color: accentColor,
              fontSize: '0.75rem', fontWeight: 700, cursor: 'pointer',
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
