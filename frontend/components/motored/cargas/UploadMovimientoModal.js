'use client';
/**
 * frontend/components/motored/cargas/UploadMovimientoModal.js
 *
 * One-step upload dialog for ONE declared movement `tipo` (sdd/motored-
 * cargas-tipo-declarado; design D3). Replaces `UploadCargaModal.js`'s
 * 2-step machinery (`useSubidaInicial`/`useCompletarCarga`/`SelectorTipo`/
 * `PasoSubir`/`PasoCompletar`, all retired) -- there is nothing left to
 * complete in a second step: `tipo` is already known BEFORE the file is
 * even chosen, because the caller is `MovimientoTab`, itself parameterized
 * by `tipo`. Period fields (only when `tipoDeclaraPeriodo(tipo)`) render
 * up front, and `POST /cargas` either succeeds outright or is rejected
 * with a named reason -- never "PENDIENTE waiting for a human to pick a
 * type", which is structurally impossible now (design D1).
 */
import { useState } from 'react';
import { subirCargaMovimiento, getCarga } from '../../../lib/motored/api';
import InfoTooltip from '../InfoTooltip';
import { tipoDeclaraPeriodo, excedeUnMes } from './tiposCarga';

const overlayStyle = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200,
};

const boxStyle = {
  background: 'var(--motored-surface, #ffffff)',
  border: '1px solid var(--motored-border, #e4e4e7)',
  borderRadius: 'var(--motored-radius-md, 8px)',
  padding: '1.5rem', width: '100%', maxWidth: '560px', maxHeight: '90vh',
  overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem',
};

const labelStyle = {
  display: 'flex', flexDirection: 'column', gap: '0.3rem', fontSize: '0.75rem',
  color: 'var(--motored-text-muted, #5a5a5a)',
};

function PeriodoNotice({ periodoDesde, periodoHasta }) {
  if (!excedeUnMes(periodoDesde, periodoHasta)) return null;
  return (
    <p
      role="alert"
      style={{
        margin: 0, padding: '0.5rem 0.75rem', fontSize: '0.75rem', fontWeight: 600,
        color: 'var(--motored-warning, #d97706)', background: 'var(--motored-warning-bg, #fef3e2)',
        borderRadius: 'var(--motored-radius-sm, 4px)',
      }}
    >
      Cargas recurrentes: un mes por archivo.
    </p>
  );
}

function CamposPeriodo({ periodoDesde, setPeriodoDesde, periodoHasta, setPeriodoHasta, disabled }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <div style={{ display: 'flex', gap: '0.75rem' }}>
        <label style={labelStyle}>
          <span>
            Período declarado — desde
            <InfoTooltip text="La fecha que VOS declarás que representa este archivo. El sistema la usa como verdad y, cuando puede, la compara contra las fechas que trae el archivo para avisar si no coinciden." />
          </span>
          <input type="date" value={periodoDesde} onChange={(e) => setPeriodoDesde(e.target.value)} disabled={disabled} />
        </label>
        <label style={labelStyle}>
          <span>
            Período declarado — hasta (opcional)
            <InfoTooltip text="Dejalo vacío si el archivo es de un solo día o un solo mes: se usa el mismo valor de 'desde'." />
          </span>
          <input type="date" value={periodoHasta} onChange={(e) => setPeriodoHasta(e.target.value)} disabled={disabled} />
        </label>
      </div>
      <PeriodoNotice periodoDesde={periodoDesde} periodoHasta={periodoHasta} />
    </div>
  );
}

function useSubirMovimiento(tipo, onUploaded) {
  const [file, setFile] = useState(null);
  const [periodoDesde, setPeriodoDesde] = useState('');
  const [periodoHasta, setPeriodoHasta] = useState('');
  const [duplicadoInfo, setDuplicadoInfo] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [completo, setCompleto] = useState(false);

  const necesitaPeriodo = tipoDeclaraPeriodo(tipo);

  const handleSubir = async () => {
    if (!file) return;
    if (necesitaPeriodo && !periodoDesde) {
      setError('Declará el período de este archivo antes de continuar.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const res = await subirCargaMovimiento(file, tipo, {
        periodoDesde, periodoHasta: periodoHasta || periodoDesde,
      });
      if (res.duplicado_de) {
        try {
          const previa = await getCarga(res.duplicado_de);
          setDuplicadoInfo(
            `Ya existe una carga idéntica del ${new Date(previa.created_at).toLocaleDateString('es-CO')}. Igual podés continuar.`
          );
        } catch {
          setDuplicadoInfo('Ya existe una carga idéntica anterior. Igual podés continuar.');
        }
      }
      setCompleto(true);
      onUploaded?.();
    } catch (err) {
      setError(err.message || 'No se pudo subir el archivo');
    } finally {
      setLoading(false);
    }
  };

  return {
    file, setFile, periodoDesde, setPeriodoDesde, periodoHasta, setPeriodoHasta,
    necesitaPeriodo, duplicadoInfo, loading, error, completo, handleSubir,
  };
}

function ConfirmacionCarga({ duplicadoInfo, onClose }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {duplicadoInfo && (
        <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--motored-warning, #d97706)' }}>
          {duplicadoInfo}
        </p>
      )}
      <p style={{ margin: 0, fontSize: '0.85rem', fontWeight: 700, color: 'var(--motored-success, #15803d)' }}>
        Carga recibida. Vas a verla en la historia con su estado actualizándose solo.
      </p>
      <button type="button" className="motored-btn motored-btn-secondary" onClick={onClose}>
        Listo
      </button>
    </div>
  );
}

function ZonaArchivo({ file, setFile, label }) {
  return (
    <label
      style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        gap: '0.4rem', padding: '1.5rem', border: '2px dashed var(--motored-border, #e4e4e7)',
        borderRadius: 'var(--motored-radius-md, 8px)', background: 'var(--motored-surface-alt, #f4f4f5)',
        cursor: 'pointer', textAlign: 'center',
      }}
    >
      <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--motored-text, #1a1a18)' }}>
        {file?.name || `Hacé clic acá para elegir el archivo Excel (.xlsx) de ${label}`}
      </span>
      <input
        type="file"
        accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        style={{ display: 'none' }}
        onChange={(e) => setFile(e.target.files?.[0] || null)}
      />
    </label>
  );
}

function FormularioSubida({ estado, onSubir }) {
  const {
    file, setFile, periodoDesde, setPeriodoDesde, periodoHasta, setPeriodoHasta,
    necesitaPeriodo, loading, label,
  } = estado;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <ZonaArchivo file={file} setFile={setFile} label={label} />

      {necesitaPeriodo && (
        <CamposPeriodo
          periodoDesde={periodoDesde} setPeriodoDesde={setPeriodoDesde}
          periodoHasta={periodoHasta} setPeriodoHasta={setPeriodoHasta}
        />
      )}

      <button type="button" className="motored-btn motored-btn-primary" onClick={onSubir} disabled={loading || !file}>
        {loading ? 'Subiendo...' : 'Subir archivo'}
      </button>
    </div>
  );
}

export default function UploadMovimientoModal({ tipo, label, onClose, onUploaded }) {
  const estado = useSubirMovimiento(tipo, onUploaded);
  const { duplicadoInfo, error, completo, handleSubir } = estado;

  return (
    <div role="dialog" aria-label={`Subir ${label}`} style={overlayStyle}>
      <div style={boxStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 800, color: 'var(--motored-text, #1a1a18)' }}>
            Subir {label}
          </h2>
          <button type="button" className="motored-btn motored-btn-tertiary" onClick={onClose}>
            Cerrar
          </button>
        </div>

        {error && <p style={{ margin: 0, color: 'var(--motored-danger, #c0392b)', fontSize: '0.75rem' }}>{error}</p>}

        {completo ? (
          <ConfirmacionCarga duplicadoInfo={duplicadoInfo} onClose={onClose} />
        ) : (
          <FormularioSubida estado={{ ...estado, label }} onSubir={handleSubir} />
        )}
      </div>
    </div>
  );
}
