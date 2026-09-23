'use client';
/**
 * frontend/components/motored/cargas/UploadCargaModal.js
 *
 * Shared drop zone for los 8 `tipo` de `carga_archivo` (sdd/motored-
 * pedidos-ingesta, Phase 10, task 10.1; spec "Shared drop zone and history
 * for all carga types" + "File type detection with manual override" +
 * "Duplicate hash never blocks"; design ADR-9).
 *
 * Estructura calcada de `maestros/BulkUploadModal.js` (overlay+box, header
 * con título+cerrar, `motored-btn` para las acciones) -- pero NO es la
 * misma política (ADR-5): acá la subida es en 2 pasos porque el `tipo` lo
 * detecta el SERVIDOR por firma de encabezado (`POST /cargas` nunca recibe
 * `tipo` en el body), así que el período solo puede pedirse con una forma
 * conocida (mes vs. fecha única) DESPUÉS de saber el tipo resuelto:
 *
 *   Paso 1 "subir": el usuario elige el archivo y, opcionalmente, un rango
 *   de fechas genérico (`periodo_desde`/`periodo_hasta`) -- útil cuando ya
 *   sabe qué período está declarando (p.ej. "esto es Ventas de
 *   septiembre"). Se manda todo junto en el mismo `POST` (ADR-9: el
 *   período puede declararse sin conocer el tipo todavía).
 *
 *   Paso 2 "completar" (SOLO si el servidor responde `requiere_tipo` o
 *   `requiere_periodo`, o si el usuario pide corregir el tipo detectado --
 *   spec "the user...can override it, before any row is validated"): un
 *   select de tipo (obligatorio si no se detectó) + los mismos campos de
 *   período, ahora ya sabiendo si el tipo resuelto declara período o no
 *   (`tipoDeclaraPeriodo`), enviados vía `PATCH /cargas/{id}` -- la carga
 *   queda `PENDIENTE`, sin ser reclamada por el supervisor, hasta que este
 *   paso se completa (design "Gating: how a load waits for its period").
 *
 * `MAESTRO_REFERENCIAS`/`MAESTRO_BODEGAS` SIEMPRE caen en el paso 2 con
 * tipo obligatorio -- `deteccion.py` los excluye a propósito de la
 * detección automática (firma demasiado genérica).
 */
import { useState } from 'react';
import { subirCargaMovimiento, completarCarga, getCarga } from '../../../lib/motored/api';
import InfoTooltip from '../InfoTooltip';
import { TIPOS_CARGA, tipoDeclaraPeriodo, excedeUnMes } from './tiposCarga';

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

function useSubidaInicial(onUploaded) {
  const [file, setFile] = useState(null);
  const [periodoDesde, setPeriodoDesde] = useState('');
  const [periodoHasta, setPeriodoHasta] = useState('');
  const [subida, setSubida] = useState(null); // respuesta 202 de POST /cargas
  const [duplicadoInfo, setDuplicadoInfo] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubir = async () => {
    if (!file) return;
    setLoading(true);
    setError('');
    try {
      const res = await subirCargaMovimiento(file, { periodoDesde, periodoHasta: periodoHasta || periodoDesde });
      setSubida(res);
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
      // Paso 2 nunca se monta si el servidor ya resolvió tipo/período --
      // este hook es el único responsable de avisar en ese caso.
      if (!res.requiere_tipo && !res.requiere_periodo) {
        onUploaded?.();
      }
    } catch (err) {
      setError(err.message || 'No se pudo subir el archivo');
    } finally {
      setLoading(false);
    }
  };

  return {
    file, setFile, periodoDesde, setPeriodoDesde, periodoHasta, setPeriodoHasta,
    subida, duplicadoInfo, loading, error, handleSubir,
  };
}

function useCompletarCarga(subida, periodoYaDeclarado, onUploaded) {
  const [tipoElegido, setTipoElegido] = useState(subida?.tipo_detectado || '');
  const [cambiarTipo, setCambiarTipo] = useState(false);
  const [periodoDesde2, setPeriodoDesde2] = useState('');
  const [periodoHasta2, setPeriodoHasta2] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [completo, setCompleto] = useState(false);

  const tipoEfectivo = subida?.requiere_tipo ? tipoElegido : (subida?.tipo_detectado || '');
  const necesitaPeriodoAhora = !periodoYaDeclarado && tipoDeclaraPeriodo(tipoEfectivo);

  const handleCompletar = async () => {
    if (subida.requiere_tipo && !tipoElegido) {
      setError('Elegí un tipo de archivo antes de continuar.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const payload = {};
      if (subida.requiere_tipo || (cambiarTipo && tipoElegido)) payload.tipo = tipoElegido;
      if (necesitaPeriodoAhora) {
        if (!periodoDesde2) {
          setError('Declará el período de este archivo antes de continuar.');
          return;
        }
        payload.periodo_desde = periodoDesde2;
        payload.periodo_hasta = periodoHasta2 || periodoDesde2;
      }
      await completarCarga(subida.carga_id, payload);
      setCompleto(true);
      onUploaded?.();
    } catch (err) {
      setError(err.message || 'No se pudo completar la carga');
    } finally {
      setLoading(false);
    }
  };

  return {
    tipoElegido, setTipoElegido, cambiarTipo, setCambiarTipo,
    periodoDesde2, setPeriodoDesde2, periodoHasta2, setPeriodoHasta2,
    tipoEfectivo, necesitaPeriodoAhora, loading, error, completo, handleCompletar,
  };
}

function SelectorTipo({ value, onChange, required = false }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} required={required}>
      <option value="" style={{ color: '#1a1a18' }}>— Elegir —</option>
      {TIPOS_CARGA.map((t) => (
        <option key={t.value} value={t.value} style={{ color: '#1a1a18' }}>{t.label}</option>
      ))}
    </select>
  );
}

function PasoSubir({ estado, onSubir }) {
  const { file, setFile, periodoDesde, setPeriodoDesde, periodoHasta, setPeriodoHasta, loading } = estado;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <label
        style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          gap: '0.4rem', padding: '1.5rem', border: '2px dashed var(--motored-border, #e4e4e7)',
          borderRadius: 'var(--motored-radius-md, 8px)', background: 'var(--motored-surface-alt, #f4f4f5)',
          cursor: 'pointer', textAlign: 'center',
        }}
      >
        <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--motored-text, #1a1a18)' }}>
          {file?.name || 'Hacé clic acá para elegir el archivo Excel (.xlsx)'}
        </span>
        <span style={{ fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          Ventas, inventario, backorder, facturas, ingresos, demanda perdida o maestros — todos
          entran por acá. El sistema detecta el tipo automáticamente cuando puede.
        </span>
        <input
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          style={{ display: 'none' }}
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
      </label>

      <CamposPeriodo
        periodoDesde={periodoDesde} setPeriodoDesde={setPeriodoDesde}
        periodoHasta={periodoHasta} setPeriodoHasta={setPeriodoHasta}
      />

      <button type="button" className="motored-btn motored-btn-primary" onClick={onSubir} disabled={loading || !file}>
        {loading ? 'Subiendo...' : 'Subir archivo'}
      </button>
    </div>
  );
}

function PasoCompletar({ estado, onCompletar }) {
  const {
    subida, duplicadoInfo, tipoElegido, setTipoElegido, cambiarTipo, setCambiarTipo,
    periodoDesde2, setPeriodoDesde2, periodoHasta2, setPeriodoHasta2, tipoEfectivo,
    necesitaPeriodoAhora, loading,
  } = estado;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      {duplicadoInfo && (
        <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--motored-warning, #d97706)' }}>
          {duplicadoInfo}
        </p>
      )}

      {subida.requiere_tipo ? (
        <label style={labelStyle}>
          <span>
            Tipo de archivo (no se pudo detectar automáticamente)
            <InfoTooltip text="El sistema no reconoció los encabezados de este archivo (o es un maestro, que siempre requiere selección manual). Elegí el tipo correcto para poder continuar." />
          </span>
          <SelectorTipo value={tipoElegido} onChange={setTipoElegido} required />
        </label>
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem' }}>
          <span>
            Tipo detectado: <strong>{TIPOS_CARGA.find((t) => t.value === subida.tipo_detectado)?.label || subida.tipo_detectado}</strong>
          </span>
          <button type="button" className="motored-btn motored-btn-tertiary" onClick={() => setCambiarTipo((v) => !v)}>
            {cambiarTipo ? 'Cancelar cambio' : 'Cambiar tipo'}
          </button>
        </div>
      )}

      {!subida.requiere_tipo && cambiarTipo && (
        <SelectorTipo value={tipoElegido} onChange={setTipoElegido} />
      )}

      {necesitaPeriodoAhora && (
        <CamposPeriodo
          periodoDesde={periodoDesde2} setPeriodoDesde={setPeriodoDesde2}
          periodoHasta={periodoHasta2} setPeriodoHasta={setPeriodoHasta2}
        />
      )}

      {!tipoEfectivo && !subida.requiere_tipo && (
        <p style={{ margin: 0, fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          Elegí un tipo para saber si este archivo necesita declarar un período.
        </p>
      )}

      <button type="button" className="motored-btn motored-btn-primary" onClick={onCompletar} disabled={loading}>
        {loading ? 'Guardando...' : 'Guardar y continuar'}
      </button>
    </div>
  );
}

export default function UploadCargaModal({ onClose, onUploaded }) {
  const subida1 = useSubidaInicial(onUploaded);
  const { subida } = subida1;
  const periodoYaDeclarado = Boolean(subida1.periodoDesde);
  const paso2 = useCompletarCarga(subida, periodoYaDeclarado, onUploaded);

  const completoDirecto = Boolean(subida) && !subida.requiere_tipo && !subida.requiere_periodo;
  const completo = completoDirecto || paso2.completo;
  const necesitaCompletar = subida && (subida.requiere_tipo || subida.requiere_periodo) && !completo;
  const error = necesitaCompletar || completo ? paso2.error : subida1.error;

  return (
    <div role="dialog" aria-label="Subir carga" style={overlayStyle}>
      <div style={boxStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 800, color: 'var(--motored-text, #1a1a18)' }}>
            Subir carga
          </h2>
          <button type="button" className="motored-btn motored-btn-tertiary" onClick={onClose}>
            Cerrar
          </button>
        </div>

        {error && <p style={{ margin: 0, color: 'var(--motored-danger, #c0392b)', fontSize: '0.75rem' }}>{error}</p>}

        {completo ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <p style={{ margin: 0, fontSize: '0.85rem', fontWeight: 700, color: 'var(--motored-success, #15803d)' }}>
              Carga recibida. Vas a verla en la historia con su estado actualizándose solo.
            </p>
            <button type="button" className="motored-btn motored-btn-secondary" onClick={onClose}>
              Listo
            </button>
          </div>
        ) : necesitaCompletar ? (
          <PasoCompletar estado={{ ...subida1, ...paso2 }} onCompletar={paso2.handleCompletar} />
        ) : (
          <PasoSubir estado={subida1} onSubir={subida1.handleSubir} />
        )}
      </div>
    </div>
  );
}
