'use client';
import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle, X } from 'lucide-react';
import { authFetch } from '../../lib/authFetch';
import { toast } from '../../lib/toast';
import ConfirmModal from '../ConfirmModal';

/**
 * Superadmin resolution flow for a description edit on a `part_number` with
 * no matching `PartsReference` yet (`sdd/parts-description-source-of-truth`
 * PR3, spec's "Not-Yet-Cataloged Code — Superadmin Path", design D4/D5).
 * Opened when `EditableCell`/`EditableReconciliationCell`'s save attempt
 * gets a 409 `PART_NOT_IN_CATALOG`. Search is always scoped to the edited
 * row's own `model_applicable` -- never catalog-wide (spec).
 *
 * Props:
 * - partNumber: the uncatalogued code
 * - modelApplicable: the row's vehicle model, for the scoped search
 * - pendingDescription: the ES text the superadmin was trying to save --
 *   persisted through the shared write path as soon as link/create resolves
 * - onClose: close without resolving
 * - onResolved: called after a successful link or create, so the caller
 *   can refetch its list
 */
export default function CodeCandidateModal({ partNumber, modelApplicable, pendingDescription, onClose, onResolved }) {
  const [loading, setLoading] = useState(true);
  const [candidates, setCandidates] = useState([]);
  const [fetchError, setFetchError] = useState(false);
  const [pendingLink, setPendingLink] = useState(null);
  const [busy, setBusy] = useState(false);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setFetchError(false);
      try {
        const params = new URLSearchParams({ part_number: partNumber, model_applicable: modelApplicable || '' });
        const res = await authFetch(`/parts/admin/code-candidates?${params}`);
        if (!res.ok) throw new Error('No se pudieron buscar repuestos similares');
        const data = await res.json().catch(() => []);
        if (!cancelled) setCandidates(Array.isArray(data) ? data : []);
      } catch {
        if (!cancelled) {
          setCandidates([]);
          setFetchError(true);
          toast.error('No se pudieron buscar repuestos similares. Intentá de nuevo.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [partNumber, modelApplicable, retryToken]);

  const extractError = async (res) => {
    const data = await res.json().catch(() => ({}));
    const detail = data?.detail;
    return typeof detail === 'string' ? detail : detail?.detail || 'Error al resolver el código';
  };

  const doLink = async (candidate) => {
    setBusy(true);
    try {
      const res = await authFetch('/parts/admin/code-candidates/link', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          part_number: partNumber,
          existing_code: candidate.factory_part_number,
          description_es_manual: pendingDescription ?? null,
        }),
      });
      if (!res.ok) throw new Error(await extractError(res));
      toast.success(`Código ${partNumber} vinculado a ${candidate.factory_part_number}`);
      setPendingLink(null);
      onResolved?.();
    } catch (err) {
      toast.error(err.message || 'Error al vincular el código');
    } finally {
      setBusy(false);
    }
  };

  const doCreate = async () => {
    setBusy(true);
    try {
      const res = await authFetch('/parts/admin/code-candidates/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          part_number: partNumber,
          description_es_manual: pendingDescription ?? null,
        }),
      });
      if (!res.ok) throw new Error(await extractError(res));
      toast.success(`Código ${partNumber} creado en el catálogo`);
      onResolved?.();
    } catch (err) {
      toast.error(err.message || 'Error al crear el código');
    } finally {
      setBusy(false);
    }
  };

  return createPortal(
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 9998,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(0,0,0,0.72)', backdropFilter: 'blur(4px)',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#13131f', border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: 12, padding: '1.5rem', width: '100%', maxWidth: 480,
          margin: '0 1rem', boxShadow: '0 24px 48px rgba(0,0,0,0.6)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
          <div>
            <p style={{ margin: 0, fontSize: '0.85rem', fontWeight: 700, color: '#f1f5f9' }}>
              Código no catalogado
            </p>
            <p style={{ margin: '4px 0 0', fontSize: '0.75rem', color: 'rgba(255,255,255,0.6)' }}>
              <strong style={{ color: '#60a5fa', fontFamily: 'monospace' }}>{partNumber}</strong> todavía no tiene una
              referencia en el catálogo. Vinculalo a un repuesto existente o creá uno nuevo.
            </p>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)', cursor: 'pointer', padding: 4 }}
            aria-label="Cerrar"
          >
            <X size={16} />
          </button>
        </div>

        {loading ? (
          <p style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)', textAlign: 'center', margin: '1rem 0' }}>
            Buscando candidatos...
          </p>
        ) : fetchError ? (
          <div style={{ margin: '0.5rem 0 1rem' }}>
            <p style={{ fontSize: '0.75rem', color: '#f87171', margin: '0 0 8px' }}>
              No se pudieron buscar repuestos similares. Intentá de nuevo.
            </p>
            <button
              onClick={() => setRetryToken((t) => t + 1)}
              style={{
                padding: '0.35rem 0.8rem', background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.15)', borderRadius: 6,
                color: 'rgba(255,255,255,0.8)', fontSize: '0.7rem', fontWeight: 600, cursor: 'pointer',
              }}
            >
              Reintentar
            </button>
          </div>
        ) : candidates.length === 0 ? (
          <p style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)', margin: '0.5rem 0 1rem' }}>
            No se encontraron repuestos similares para este modelo.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '1rem', maxHeight: 260, overflowY: 'auto' }}>
            {candidates.map((c) => (
              <div
                key={c.factory_part_number}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '8px 10px', borderRadius: 8, background: 'rgba(255,255,255,0.04)',
                  border: '1px solid rgba(255,255,255,0.08)',
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <p style={{ margin: 0, fontSize: '0.75rem', fontWeight: 700, color: '#60a5fa', fontFamily: 'monospace' }}>
                    {c.factory_part_number}
                  </p>
                  <p style={{ margin: '2px 0 0', fontSize: '0.7rem', color: 'rgba(255,255,255,0.6)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {c.description_es_manual || c.description || '—'}
                  </p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                  <span style={{ fontSize: '0.65rem', color: '#a78bfa', fontWeight: 700 }}>
                    {Math.round(c.similarity_score * 100)}%
                  </span>
                  <button
                    disabled={busy}
                    onClick={() => setPendingLink(c)}
                    style={{
                      padding: '4px 10px', borderRadius: 6, border: '1px solid rgba(96,165,250,0.35)',
                      background: 'rgba(96,165,250,0.12)', color: '#60a5fa',
                      fontSize: '0.7rem', fontWeight: 700, cursor: busy ? 'wait' : 'pointer',
                    }}
                  >
                    Vincular
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', alignItems: 'center' }}>
          <AlertTriangle size={14} color="#fb923c" style={{ marginRight: 'auto' }} />
          <span style={{ fontSize: '0.68rem', color: 'rgba(255,255,255,0.4)', marginRight: 'auto' }}>
            Vincular mueve el historial de costos del código elegido
          </span>
          <button
            onClick={onClose}
            style={{
              padding: '0.45rem 1rem', background: 'rgba(255,255,255,0.05)',
              border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6,
              color: 'rgba(255,255,255,0.6)', fontSize: '0.75rem', fontWeight: 600, cursor: 'pointer',
            }}
          >
            Cancelar
          </button>
          <button
            disabled={busy}
            onClick={doCreate}
            style={{
              padding: '0.45rem 1rem', background: 'rgba(52,211,153,0.12)',
              border: '1px solid rgba(52,211,153,0.35)', borderRadius: 6,
              color: '#34d399', fontSize: '0.75rem', fontWeight: 700, cursor: busy ? 'wait' : 'pointer',
            }}
          >
            Crear código nuevo
          </button>
        </div>
      </div>

      {pendingLink && (
        <ConfirmModal
          title="Vincular código"
          message={`Esto va a mover el historial de costos de ${pendingLink.factory_part_number} a ${partNumber}. Esta acción no se puede deshacer.\n¿Confirmar?`}
          danger
          confirmLabel="Sí, vincular"
          onCancel={() => setPendingLink(null)}
          onConfirm={() => doLink(pendingLink)}
        />
      )}
    </div>,
    document.body
  );
}
