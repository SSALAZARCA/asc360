'use client';
/**
 * frontend/components/motored/maestros/BulkUploadModal.js
 *
 * Bulk-upload flow for one masters entity (sdd/motored-pedidos-cimientos,
 * Phase 6, task 6.3/6.4, design ADR-6). Talks to the REAL contract exposed
 * by `backend/app/motored/api/carga.py`: `filas` is an array of
 * already-structured row objects (`list[dict]`) -- there is NO client-side
 * `.xlsx` parser here, deliberately, per the proposal/design scope (Fase 1
 * "carga masiva" is a small synchronous JSON-rows upload, not the §5/§9
 * streaming pipeline). Rows are entered as pasted JSON, matching exactly
 * what the backend already accepts.
 *
 * Owner decision #1 (all-or-nothing) means a `carga`/`validar` response can
 * be `{ ok: false, errores: [{ fila, motivo }, ...] }` with MULTIPLE rows
 * reported at once (never fail-fast) -- this component's one hard
 * requirement (task 6.4) is to render EVERY row in `errores`, not just a
 * generic "upload failed" banner.
 */
import { useState } from 'react';
import { validarCarga, subirCarga } from '../../../lib/motored/api';

function CargaResultPanel({ resultado }) {
  if (!resultado) return null;

  if (resultado.ok) {
    return (
      <div style={{ color: 'var(--motored-success, #34d399)', fontSize: '0.8rem', fontWeight: 700 }}>
        OK — {resultado.total_filas} filas procesadas
        {typeof resultado.insertados === 'number' && ` (${resultado.insertados} nuevas, ${resultado.actualizados} actualizadas)`}
      </div>
    );
  }

  return (
    <div>
      <p style={{ margin: '0 0 0.5rem', color: 'var(--motored-danger, #f87171)', fontSize: '0.8rem', fontWeight: 700 }}>
        Archivo rechazado — {resultado.errores?.length ?? 0} fila(s) con error. No se escribió nada.
      </p>
      <ul data-testid="carga-error-list" style={{ margin: 0, padding: '0 0 0 1.25rem', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
        {(resultado.errores || []).map((err, idx) => (
          <li
            key={`${err.fila}-${idx}`}
            data-testid="carga-error-row"
            style={{ color: 'var(--motored-text, #e6f4ff)', fontSize: '0.75rem' }}
          >
            Fila {err.fila}: {err.motivo}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function BulkUploadModal({ entidad, onClose, onSuccess }) {
  const [rowsText, setRowsText] = useState('');
  const [parseError, setParseError] = useState('');
  const [resultado, setResultado] = useState(null);
  const [loading, setLoading] = useState(false);

  const parseRows = () => {
    try {
      const parsed = JSON.parse(rowsText);
      if (!Array.isArray(parsed)) {
        setParseError('El contenido debe ser un array JSON de filas');
        return null;
      }
      setParseError('');
      return parsed;
    } catch {
      setParseError('JSON inválido');
      return null;
    }
  };

  const runValidar = async () => {
    const filas = parseRows();
    if (!filas) return;
    setLoading(true);
    setResultado(null);
    try {
      const res = await validarCarga(entidad, filas);
      setResultado(res);
    } catch (e) {
      setResultado({ ok: false, errores: [{ fila: 0, motivo: e.message }] });
    } finally {
      setLoading(false);
    }
  };

  const runCarga = async () => {
    const filas = parseRows();
    if (!filas) return;
    setLoading(true);
    setResultado(null);
    try {
      const res = await subirCarga(entidad, filas);
      setResultado(res);
      if (res.ok) {
        onSuccess?.(res);
      }
    } catch (e) {
      setResultado({ ok: false, errores: [{ fila: 0, motivo: e.message }] });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-label={`Carga masiva de ${entidad}`}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 200,
      }}
    >
      <div
        style={{
          background: 'var(--motored-surface, #101d2e)',
          border: '1px solid var(--motored-border, rgba(148,197,255,0.12))',
          borderRadius: '12px',
          padding: '1.5rem',
          width: '100%',
          maxWidth: '560px',
          maxHeight: '85vh',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '1rem',
        }}
      >
        <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 800, color: 'var(--motored-text, #e6f4ff)' }}>
          Carga masiva — {entidad}
        </h2>

        <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--motored-text-muted, #7fa3c4)' }}>
          Pegá un array JSON de filas. Todo-o-nada: si una sola fila es
          inválida, no se escribe nada.
        </p>

        <textarea
          value={rowsText}
          onChange={(e) => setRowsText(e.target.value)}
          placeholder='[{"nombre": "CALI NORTE", "sic": "123"}]'
          rows={8}
          style={{
            width: '100%',
            fontFamily: 'monospace',
            fontSize: '0.75rem',
            background: '#0a1420',
            color: 'var(--motored-text, #e6f4ff)',
            border: '1px solid var(--motored-border, rgba(148,197,255,0.12))',
            borderRadius: '8px',
            padding: '0.75rem',
          }}
        />

        {parseError && (
          <p style={{ margin: 0, color: 'var(--motored-danger, #f87171)', fontSize: '0.75rem' }}>{parseError}</p>
        )}

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button type="button" onClick={runValidar} disabled={loading}>
            {loading ? 'Validando...' : 'Validar'}
          </button>
          <button type="button" onClick={runCarga} disabled={loading}>
            {loading ? 'Cargando...' : 'Cargar'}
          </button>
          <button type="button" onClick={onClose} disabled={loading}>
            Cerrar
          </button>
        </div>

        <CargaResultPanel resultado={resultado} />
      </div>
    </div>
  );
}
