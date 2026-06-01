'use client';
import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { CheckCircle, XCircle, Info, X } from 'lucide-react';

let _id = 0;

const TYPE_CFG = {
  error:   { icon: XCircle,       color: '#f87171', bg: 'rgba(248,113,113,0.12)', border: 'rgba(248,113,113,0.3)' },
  success: { icon: CheckCircle,   color: '#4ade80', bg: 'rgba(74,222,128,0.10)', border: 'rgba(74,222,128,0.3)'  },
  info:    { icon: Info,           color: '#60a5fa', bg: 'rgba(96,165,250,0.10)', border: 'rgba(96,165,250,0.3)'  },
};

function ToastItem({ t, onClose }) {
  const cfg = TYPE_CFG[t.type] ?? TYPE_CFG.info;
  const Icon = cfg.icon;

  return (
    <div
      style={{
        display: 'flex', alignItems: 'flex-start', gap: '0.6rem',
        padding: '0.75rem 0.9rem',
        background: '#13131f',
        border: `1px solid ${cfg.border}`,
        borderLeft: `3px solid ${cfg.color}`,
        borderRadius: 8,
        boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
        maxWidth: 360, minWidth: 240,
        animation: 'toast-in 0.2s ease',
      }}
    >
      <Icon size={15} color={cfg.color} style={{ flexShrink: 0, marginTop: 1 }} />
      <span style={{ flex: 1, fontSize: '0.78rem', color: 'rgba(255,255,255,0.85)', lineHeight: 1.5 }}>
        {t.message}
      </span>
      <button
        onClick={onClose}
        style={{ flexShrink: 0, background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'rgba(255,255,255,0.3)', marginTop: 1 }}
      >
        <X size={13} />
      </button>
    </div>
  );
}

export default function ToastContainer() {
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    const handler = (e) => {
      const id = ++_id;
      const { type, message } = e.detail;
      setToasts(prev => [...prev, { id, type, message }]);
      setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 4500);
    };
    window.addEventListener('app-toast', handler);
    return () => window.removeEventListener('app-toast', handler);
  }, []);

  if (toasts.length === 0 || typeof window === 'undefined') return null;

  return createPortal(
    <>
      <style>{`
        @keyframes toast-in {
          from { opacity: 0; transform: translateX(16px); }
          to   { opacity: 1; transform: translateX(0); }
        }
      `}</style>
      <div style={{ position: 'fixed', bottom: 24, right: 24, zIndex: 99999, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {toasts.map(t => (
          <ToastItem key={t.id} t={t} onClose={() => setToasts(prev => prev.filter(x => x.id !== t.id))} />
        ))}
      </div>
    </>,
    document.body
  );
}
