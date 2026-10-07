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
 *
 * "Descargar plantilla": downloads the `.xlsx` template the BACKEND
 * generates for this tipo (`descargarPlantillaMovimiento`) -- the backend
 * owns the column list, so it can never drift from what upload accepts.
 */
import { useState } from 'react';
import { subirCargaMovimiento, getCarga, descargarPlantillaMovimiento } from '../../../lib/motored/api';
import { fechaBogota } from '../../../lib/motored/fechas';
import InfoTooltip from '../InfoTooltip';
import { tipoDeclaraPeriodo, tipoUsaFechaDeCorte, excedeUnMes } from './tiposCarga';

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

function CampoFechaDeCorte({ fecha, setFecha, disabled }) {
  return (
    <label style={labelStyle}>
      <span>
        Fecha de corte
        <InfoTooltip text="El día de la foto del inventario: el stock que trae el archivo es el de esa fecha." />
      </span>
      <input type="date" aria-label="Fecha de corte" value={fecha} onChange={(e) => setFecha(e.target.value)} disabled={disabled} />
    </label>
  );
}

/** Informational (never blocking) notice when the same file was already uploaded. */
async function avisoDuplicado(duplicadoDe) {
  try {
    const previa = await getCarga(duplicadoDe);
    return `Ya existe una carga idéntica del ${fechaBogota(previa.created_at)}. Igual podés continuar.`;
  } catch {
    return 'Ya existe una carga idéntica anterior. Igual podés continuar.';
  }
}

/** Upload options: the declared period and, for VENTAS only, the full-month flag. */
function opcionesDeSubida(tipo, { periodoDesde, periodoHasta, fechaDeCorte, reemplazaMes }) {
  const opciones = { periodoDesde, periodoHasta: (!fechaDeCorte && periodoHasta) || periodoDesde };
  return tipo === 'VENTAS' ? { ...opciones, reemplazaMesCompleto: reemplazaMes } : opciones;
}

function useSubirMovimiento(tipo, onUploaded) {
  const [file, setFile] = useState(null);
  const [periodoDesde, setPeriodoDesde] = useState('');
  const [periodoHasta, setPeriodoHasta] = useState('');
  const [duplicadoInfo, setDuplicadoInfo] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [completo, setCompleto] = useState(false);
  const [reemplazaMes, setReemplazaMes] = useState(false);

  const necesitaPeriodo = tipoDeclaraPeriodo(tipo);
  const fechaDeCorte = tipoUsaFechaDeCorte(tipo);

  const handleDescargarPlantilla = async () => {
    setError('');
    try {
      await descargarPlantillaMovimiento(tipo);
    } catch (err) {
      setError(`No se pudo descargar la plantilla: ${err.message}`);
    }
  };

  const handleSubir = async () => {
    if (!file) return;
    if (necesitaPeriodo && !periodoDesde) {
      setError(fechaDeCorte
        ? 'Declará la fecha de corte de este archivo antes de continuar.'
        : 'Declará el período de este archivo antes de continuar.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const opciones = opcionesDeSubida(tipo, { periodoDesde, periodoHasta, fechaDeCorte, reemplazaMes });
      const res = await subirCargaMovimiento(file, tipo, opciones);
      if (res.duplicado_de) setDuplicadoInfo(await avisoDuplicado(res.duplicado_de));
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
    necesitaPeriodo, fechaDeCorte, duplicadoInfo, loading, error, completo, handleSubir, handleDescargarPlantilla,
    reemplazaMes, setReemplazaMes,
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

function CampoReemplazaMes({ marcado, setMarcado }) {
  return (
    <label style={{ ...labelStyle, flexDirection: 'row', alignItems: 'flex-start', gap: '0.5rem', cursor: 'pointer' }}>
      <input
        type="checkbox" checked={marcado} style={{ width: '24px', height: '24px', margin: '10px 0', flexShrink: 0 }}
        aria-label="Este archivo reemplaza el mes completo de toda la red"
        onChange={(e) => setMarcado(e.target.checked)}
      />
      <span style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem', paddingTop: '10px' }}>
        <span style={{ fontWeight: 700, color: 'var(--motored-text, #1a1a18)' }}>Este archivo reemplaza el mes completo de toda la red</span>
        <span>Borra las ventas de ese mes de las tiendas que no vienen en el archivo.</span>
      </span>
    </label>
  );
}

function FormularioSubida({ estado, onSubir }) {
  const {
    file, setFile, periodoDesde, setPeriodoDesde, periodoHasta, setPeriodoHasta,
    necesitaPeriodo, fechaDeCorte, loading, label, tipo, reemplazaMes, setReemplazaMes,
  } = estado;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <ZonaArchivo file={file} setFile={setFile} label={label} />

      {fechaDeCorte && (
        <CampoFechaDeCorte fecha={periodoDesde} setFecha={setPeriodoDesde} />
      )}
      {necesitaPeriodo && !fechaDeCorte && (
        <CamposPeriodo
          periodoDesde={periodoDesde} setPeriodoDesde={setPeriodoDesde}
          periodoHasta={periodoHasta} setPeriodoHasta={setPeriodoHasta}
        />
      )}

      {tipo === 'VENTAS' && <CampoReemplazaMes marcado={reemplazaMes} setMarcado={setReemplazaMes} />}

      <button type="button" className="motored-btn motored-btn-primary" onClick={onSubir} disabled={loading || !file}>
        {loading ? 'Subiendo...' : 'Subir archivo'}
      </button>
    </div>
  );
}

export default function UploadMovimientoModal({ tipo, label, onClose, onUploaded }) {
  const estado = useSubirMovimiento(tipo, onUploaded);
  const { duplicadoInfo, error, completo, handleSubir, handleDescargarPlantilla } = estado;

  return (
    <div role="dialog" aria-label={`Subir ${label}`} style={overlayStyle}>
      <div style={boxStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 800, color: 'var(--motored-text, #1a1a18)' }}>
            Subir {label}
          </h2>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button type="button" className="motored-btn motored-btn-tertiary" onClick={handleDescargarPlantilla}>
              Descargar plantilla
            </button>
            <button type="button" className="motored-btn motored-btn-tertiary" onClick={onClose}>
              Cerrar
            </button>
          </div>
        </div>

        {error && <p style={{ margin: 0, color: 'var(--motored-danger, #c0392b)', fontSize: '0.75rem' }}>{error}</p>}

        {completo ? (
          <ConfirmacionCarga duplicadoInfo={duplicadoInfo} onClose={onClose} />
        ) : (
          <FormularioSubida estado={{ ...estado, label, tipo }} onSubir={handleSubir} />
        )}
      </div>
    </div>
  );
}
