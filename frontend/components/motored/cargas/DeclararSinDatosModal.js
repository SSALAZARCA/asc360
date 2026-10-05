'use client';
/**
 * frontend/components/motored/cargas/DeclararSinDatosModal.js
 *
 * Confirms a "no data at this date" declaration (odd/tasks/motored-cargas-
 * sin-datos.md): when HMCL truly has no backorder, facturas or ingresos,
 * an empty file cannot be uploaded, so ADMIN/COMPRAS declare it instead.
 * The backend records it as an APLICADO carga with zero rows, with the
 * user and the date, and it can be annulled like any other carga.
 */
import { useState } from 'react';
import { declararSinDatos } from '../../../lib/motored/api';
import { textoSinDatos } from './tiposCarga';

const overlayStyle = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  zIndex: 200, padding: '16px',
};

const boxStyle = {
  background: 'var(--motored-surface, #ffffff)',
  border: '1px solid var(--motored-border, #e4e4e7)',
  borderRadius: 'var(--motored-radius-md, 8px)',
  padding: '1.5rem', width: '100%', maxWidth: '480px', maxHeight: '90vh',
  overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem',
};

const labelStyle = {
  display: 'flex', flexDirection: 'column', gap: '0.3rem',
  fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)',
};

/** Today in the browser's local time, as YYYY-MM-DD (never UTC). */
function hoyLocal() {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

export default function DeclararSinDatosModal({ tipo, label, onClose, onDeclared }) {
  const [hoy] = useState(hoyLocal);
  const [fecha, setFecha] = useState(hoy);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState('');

  const onConfirmar = async () => {
    if (!fecha) {
      setError('Elegí una fecha.');
      return;
    }
    setEnviando(true);
    setError('');
    try {
      await declararSinDatos(tipo, fecha);
      onDeclared();
      onClose();
    } catch (err) {
      setError(err.message || 'No se pudo registrar la declaración.');
      setEnviando(false);
    }
  };

  return (
    <div role="dialog" aria-label={`Declarar sin datos: ${label}`} style={overlayStyle}>
      <div style={boxStyle}>
        <h3 className="motored-h-seccion" style={{ margin: 0 }}>Declarar sin datos</h3>
        <p style={{ margin: 0, fontSize: '0.85rem' }}>
          {`Usalo solo si a esa fecha HMCL no tiene ${textoSinDatos(tipo)} pendientes. `}
          Queda registrado con tu usuario y se puede anular.
        </p>
        <label style={labelStyle}>
          Fecha
          <input
            type="date"
            value={fecha}
            max={hoy}
            onChange={(e) => setFecha(e.target.value)}
          />
        </label>
        {error && (
          <p role="alert" style={{ margin: 0, color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>
            {error}
          </p>
        )}
        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
          <button type="button" className="motored-btn motored-btn-secondary" onClick={onClose} disabled={enviando}>
            Cancelar
          </button>
          <button type="button" className="motored-btn motored-btn-primary" onClick={onConfirmar} disabled={enviando}>
            Confirmar
          </button>
        </div>
      </div>
    </div>
  );
}
