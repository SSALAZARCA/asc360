'use client';
/**
 * Accessible modal shell of the pedido dialogs: named by its title, described
 * by its summary, Escape cancels (unless a request is in flight), Tab stays
 * inside (also when the focus fell to the page), the focus moves in on open,
 * comes back after a request and returns to the trigger on close.
 * The body is a form, so Enter in a field confirms when the dialog allows it.
 */
import { useEffect, useId, useRef } from 'react';
import { errorStyle, overlayStyle, panelStyle } from './styles';

// Tablet touch target.
const botonStyle = { minHeight: '44px', minWidth: '44px' };
const ENFOCABLES = 'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled])';

function enfocables(raiz) {
  return Array.from(raiz.current.querySelectorAll(ENFOCABLES));
}

function useFoco(raiz, ocupado) {
  useEffect(() => {
    const previo = document.activeElement;
    const [primero] = enfocables(raiz);
    if (primero) primero.focus();
    return () => { if (previo && previo.focus) previo.focus(); };
  }, [raiz]);

  // A browser drops the focus of a button that gets disabled while the request runs: take it back when it ends.
  useEffect(() => {
    if (ocupado || raiz.current.contains(document.activeElement)) return;
    const [primero] = enfocables(raiz);
    if (primero) primero.focus();
  }, [ocupado, raiz]);
}

/** Keeps Tab and Shift+Tab inside the dialog, also when the focus had fallen back to the page. */
function mantenerFoco(evento, raiz) {
  const lista = enfocables(raiz);
  if (lista.length === 0) return;
  const primero = lista[0];
  const ultimo = lista[lista.length - 1];
  const dentro = raiz.current.contains(document.activeElement);
  if (!dentro) {
    evento.preventDefault();
    (evento.shiftKey ? ultimo : primero).focus();
  } else if (evento.shiftKey && document.activeElement === primero) {
    evento.preventDefault();
    ultimo.focus();
  } else if (!evento.shiftKey && document.activeElement === ultimo) {
    evento.preventDefault();
    primero.focus();
  }
}

/** Escape cancels and Tab stays inside, listening on the document so a lost focus cannot leave the dialog stuck. */
function useTeclado(raiz, ocupado, onCancel) {
  const ultimo = useRef({ ocupado, onCancel });
  ultimo.current = { ocupado, onCancel };
  useEffect(() => {
    const alTeclear = (evento) => {
      if (evento.key === 'Escape' && !ultimo.current.ocupado) ultimo.current.onCancel();
      if (evento.key === 'Tab') mantenerFoco(evento, raiz);
    };
    document.addEventListener('keydown', alTeclear);
    return () => document.removeEventListener('keydown', alTeclear);
  }, [raiz]);
}

export default function DialogoPedido({
  titulo, descripcion, children, error, ocupado, textoConfirmar, confirmarDeshabilitado = false,
  onConfirm, onCancel, ancho,
}) {
  const id = useId();
  const raiz = useRef(null);
  useFoco(raiz, ocupado);
  useTeclado(raiz, ocupado, onCancel);

  const alEnviar = (evento) => {
    evento.preventDefault();
    if (!ocupado && !confirmarDeshabilitado) onConfirm();
  };

  return (
    <div style={overlayStyle}>
      <div
        ref={raiz} role="dialog" aria-modal="true" aria-labelledby={`${id}-titulo`}
        aria-describedby={`${id}-descripcion`} style={{ ...panelStyle, ...(ancho ? { maxWidth: ancho } : {}) }}
      >
        <h2 id={`${id}-titulo`} className="motored-h-seccion">{titulo}</h2>
        <form onSubmit={alEnviar} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div id={`${id}-descripcion`} style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.85rem' }}>
            {descripcion}
          </div>
          {children}
          {error && <p role="alert" style={errorStyle}>{error}</p>}
          <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
            <button type="button" className="motored-btn motored-btn-secondary" style={botonStyle} onClick={onCancel} disabled={ocupado}>
              Cancelar
            </button>
            <button type="submit" className="motored-btn motored-btn-primary" style={botonStyle} disabled={ocupado || confirmarDeshabilitado}>
              {textoConfirmar}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
