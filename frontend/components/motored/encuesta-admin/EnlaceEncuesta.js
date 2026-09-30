'use client';
/** Read-only public survey URL with a copy button (T7). */
import { useEffect, useState } from 'react';
import { Copy } from 'lucide-react';
import { cardStyle } from './styles';

export default function EnlaceEncuesta() {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  const url = typeof window !== 'undefined' ? `${window.location.origin}/motored/encuesta` : '';

  useEffect(() => {
    if (!copied) return undefined;
    const timer = setTimeout(() => setCopied(false), 2500);
    return () => clearTimeout(timer);
  }, [copied]);

  const copy = async () => {
    setFailed(false);
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      setFailed(true);
    }
  };

  return (
    <section style={cardStyle}>
      <h2 className="motored-h-seccion">Enlace de la encuesta</h2>
      <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Este es el enlace que se pega al final del mensaje de WhatsApp en Escala.
      </p>
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          aria-label="Enlace de la encuesta"
          readOnly
          value={url}
          onFocus={(e) => e.target.select()}
          style={{ flex: '1 1 260px', minWidth: 0 }}
        />
        <button type="button" className="motored-btn motored-btn-secondary" onClick={copy}>
          <Copy size={14} /> Copiar enlace
        </button>
        {copied && <span role="status" style={{ fontSize: '0.8rem' }}>Enlace copiado</span>}
        {failed && <span role="alert" style={{ fontSize: '0.8rem', color: 'var(--motored-danger, #c0392b)' }}>No se pudo copiar. Selecciona el enlace y cópialo a mano.</span>}
      </div>
    </section>
  );
}
