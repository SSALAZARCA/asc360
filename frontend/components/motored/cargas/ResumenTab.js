'use client';
/**
 * frontend/components/motored/cargas/ResumenTab.js
 *
 * Informe previo (sdd/motored-pedidos-ingesta, Phase 10, task 10.2; spec
 * "Two-step validar-then-aplicar con informe previo"): conteos, período
 * declarado vs. detectado (`log.periodo_detectado`, ADR-9), variación vs.
 * la carga aplicada anterior del MISMO tipo (±40%), y las acciones
 * `Aplicar`/`Anular` -- restringidas a `ADMIN`/`COMPRAS` en el servidor
 * (`require_roles`), ocultas acá para el resto por la misma razón que
 * `app/motored/cargas/page.js` oculta "Subir carga".
 */
import { useEffect, useState, useCallback } from 'react';
import { getInformeCarga, aplicarCarga, anularCarga } from '../../../lib/motored/api';
import { getRolActual } from '../../../lib/motored/motoredFetch';
import InfoTooltip from '../InfoTooltip';

function useInforme(cargaId, estadoCarga) {
  const [informe, setInforme] = useState(null);
  const [error, setError] = useState('');

  const cargar = useCallback(async () => {
    try {
      const data = await getInformeCarga(cargaId);
      setInforme(data);
      setError('');
    } catch (err) {
      setError(err.message || 'No se pudo cargar el informe');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cargaId, estadoCarga]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  return { informe, error, reload: cargar };
}

function VarianzaAviso({ variacion }) {
  if (variacion == null) return null;
  const fuerteBaja = variacion <= -40;
  return (
    <p
      style={{
        margin: 0, fontSize: '0.75rem', fontWeight: 600,
        color: fuerteBaja ? 'var(--motored-danger, #c0392b)' : 'var(--motored-text-muted, #5a5a5a)',
      }}
    >
      Variación vs. la carga anterior del mismo tipo: {variacion.toFixed(1)}%
      {fuerteBaja && ' — posible archivo incompleto'}
    </p>
  );
}

function PeriodoDetectado({ log }) {
  const detectado = log?.periodo_detectado;
  if (!detectado) return null;
  return (
    <div style={{ fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
      <span>
        Período detectado en el archivo
        <InfoTooltip text="Lo que el sistema encontró REALMENTE en la columna de fecha del archivo, comparado contra el período que vos declaraste. El declarado manda; esto es solo la evidencia." />
        : {typeof detectado === 'object' ? JSON.stringify(detectado) : String(detectado)}
      </span>
    </div>
  );
}

function Conteo({ etiqueta, valor, color }) {
  return (
    <div>
      <p className="motored-t-rotulo" style={{ margin: 0, color: 'var(--motored-text-soft, #8a8a8a)' }}>{etiqueta}</p>
      <p className="motored-mono" style={{ margin: 0, fontSize: '1.25rem', fontWeight: 700, color }}>{valor}</p>
    </div>
  );
}

function Conteos({ informe }) {
  return (
    <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
      <Conteo etiqueta="Filas leídas" valor={informe.filas_leidas} />
      <Conteo etiqueta="Filas válidas" valor={informe.filas_validas} color="var(--motored-success, #15803d)" />
      <Conteo etiqueta="Filas rechazadas" valor={informe.filas_rechazadas} color="var(--motored-danger, #c0392b)" />
    </div>
  );
}

function useAccionesCarga({ cargaId, reload, onChanged }) {
  const [accionando, setAccionando] = useState(false);
  const [accionError, setAccionError] = useState('');

  const ejecutar = useCallback(async (accion, mensajeError) => {
    setAccionando(true);
    setAccionError('');
    try {
      await accion();
      await reload();
      onChanged?.();
    } catch (err) {
      setAccionError(err.message || mensajeError);
    } finally {
      setAccionando(false);
    }
  }, [reload, onChanged]);

  return {
    accionando,
    accionError,
    handleAplicar: () => ejecutar(() => aplicarCarga(cargaId), 'No se pudo aplicar la carga'),
    handleAnular: () => {
      if (!window.confirm('¿Anular esta carga? Se borran las filas en proceso (staging); si ya está APLICADA, esta acción queda registrada para revisión de corridas futuras.')) {
        return;
      }
      return ejecutar(() => anularCarga(cargaId), 'No se pudo anular la carga');
    },
  };
}

function AccionesCarga({ estado, accionando, onAplicar, onAnular }) {
  return (
    <div style={{ display: 'flex', gap: '0.75rem' }}>
      <button
        type="button" className="motored-btn motored-btn-primary"
        onClick={onAplicar} disabled={accionando || estado !== 'VALIDADO'}
      >
        {accionando ? 'Aplicando...' : 'Aplicar'}
      </button>
      <button
        type="button" className="motored-btn motored-btn-destructive"
        onClick={onAnular} disabled={accionando || estado === 'ANULADO'}
      >
        Anular
      </button>
    </div>
  );
}

export default function ResumenTab({ carga, onChanged }) {
  const { informe, error, reload } = useInforme(carga.id, carga.estado);
  const [rol, setRol] = useState(null);
  const { accionando, accionError, handleAplicar, handleAnular } = useAccionesCarga({
    cargaId: carga.id, reload, onChanged,
  });

  useEffect(() => {
    setRol(getRolActual());
  }, []);

  const puedeEscribir = rol === 'ADMIN' || rol === 'COMPRAS';

  if (error) return <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{error}</p>;
  if (!informe) return <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>Cargando informe...</p>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <Conteos informe={informe} />

      <div style={{ fontSize: '0.8rem' }}>
        <span>
          Período declarado
          <InfoTooltip text="Lo que vos declaraste al subir el archivo. Es la fuente de verdad -- el sistema NUNCA la reemplaza sola, aunque el archivo diga otra cosa." />
          : {informe.periodo_desde ? `${informe.periodo_desde} → ${informe.periodo_hasta}` : 'No aplica para este tipo'}
        </span>
      </div>

      <PeriodoDetectado log={informe.log} />
      <VarianzaAviso variacion={informe.variacion_pct_vs_carga_anterior} />

      {accionError && <p style={{ margin: 0, color: 'var(--motored-danger, #c0392b)', fontSize: '0.75rem' }}>{accionError}</p>}

      {puedeEscribir && (
        <AccionesCarga estado={informe.estado} accionando={accionando} onAplicar={handleAplicar} onAnular={handleAnular} />
      )}
    </div>
  );
}
