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
 *
 * For ADMIN and COMPRAS, a raw ERP VENTAS carga in VALIDADO also shows its dry run
 * (`PanelVentasErp`) and, when it replaces the whole month, the tiendas
 * whose sales Aplicar deletes (`AvisoVaciado`). Aplicar stays disabled while
 * any ref has no line or that deletion is not acknowledged.
 */
import { useEffect, useState, useCallback } from 'react';
import { getInformeCarga, aplicarCarga, anularCarga } from '../../../lib/motored/api';
import { getRolActual } from '../../../lib/motored/motoredFetch';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';
import InfoTooltip from '../InfoTooltip';
import AvisoVaciado from './AvisoVaciado';
import PanelVentasErp from './PanelVentasErp';
import useSimulacionVentas from './useSimulacionVentas';

const CONFIRMAR_ANULAR = '¿Anular esta carga? Se borran las filas en proceso (staging). '
  + 'Si ya está APLICADA y la usa el pedido cerrado o enviado de alguna tienda, el sistema no permitirá anularla.';

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

/** Filas con errores que NO se cargan (las válidas sí): `log.filas_con_error`
 * (rechazadas + staged con sucursal/referencia sin resolver); cargas viejas
 * sin ese campo caen a `filas_rechazadas`. Se muestra en el informe previo y
 * también después de Aplicar, sin abrir la pestaña Errores. */
function FilasNoCargadasAviso({ informe }) {
  const cantidad = informe.log?.filas_con_error ?? informe.filas_rechazadas;
  if (!cantidad) return null;
  const sujeto = cantidad === 1 ? '1 fila con errores no se cargó.' : `${cantidad} filas con errores no se cargaron.`;
  return (
    <p
      role="alert"
      style={{
        margin: 0, padding: '0.5rem 0.75rem', fontSize: '0.8rem', fontWeight: 600,
        color: 'var(--motored-danger, #c0392b)', background: 'var(--motored-danger-bg, #fdecea)',
        borderRadius: 'var(--motored-radius-sm, 4px)',
      }}
    >
      {`${sujeto} Revisá el detalle en Errores o descargá errores.csv`}
    </p>
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
      // A coded rejection (E-CARGA-050 names the tienda and the corrida) shows its message and code.
      setAccionError(mensajeConCodigo(err, mensajeError));
    } finally {
      setAccionando(false);
    }
  }, [reload, onChanged]);

  return {
    accionando,
    accionError,
    handleAplicar: () => ejecutar(() => aplicarCarga(cargaId), 'No se pudo aplicar la carga'),
    handleAnular: () => {
      if (!window.confirm(CONFIRMAR_ANULAR)) {
        return;
      }
      return ejecutar(() => anularCarga(cargaId), 'No se pudo anular la carga');
    },
  };
}

function AccionesCarga({ estado, accionando, bloqueo, onAplicar, onAnular }) {
  return (
    <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'center' }}>
      <button
        type="button" className="motored-btn motored-btn-primary"
        onClick={onAplicar} disabled={accionando || estado !== 'VALIDADO' || bloqueo.bloqueado}
      >
        {accionando ? 'Aplicando...' : 'Aplicar'}
      </button>
      <button
        type="button" className="motored-btn motored-btn-destructive"
        onClick={onAnular} disabled={accionando || estado === 'ANULADO'}
      >
        Anular
      </button>
      {bloqueo.mensaje && (
        <p style={{ margin: 0, fontSize: '0.8rem', fontWeight: 600, color: 'var(--motored-danger, #c0392b)' }}>{bloqueo.mensaje}</p>
      )}
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
  const simulacion = useSimulacionVentas(carga, puedeEscribir);

  if (error) return <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{error}</p>;
  if (!informe) return <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>Cargando informe...</p>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <Conteos informe={informe} />
      <FilasNoCargadasAviso informe={informe} />

      <div style={{ fontSize: '0.8rem' }}>
        <span>
          Período declarado
          <InfoTooltip text="Lo que vos declaraste al subir el archivo. Es la fuente de verdad -- el sistema NUNCA la reemplaza sola, aunque el archivo diga otra cosa." />
          : {informe.periodo_desde ? `${informe.periodo_desde} → ${informe.periodo_hasta}` : 'No aplica para este tipo'}
        </span>
      </div>

      <PeriodoDetectado log={informe.log} />
      <VarianzaAviso variacion={informe.variacion_pct_vs_carga_anterior} />
      {simulacion.activa && <PanelVentasErp log={informe.log} estado={simulacion.sinLinea} puedeAsignar={puedeEscribir} />}
      {simulacion.activa && (
        <AvisoVaciado vaciado={simulacion.vaciado} entendido={simulacion.entendido} onEntendido={simulacion.setEntendido} />
      )}

      {accionError && <p role="alert" style={{ margin: 0, color: 'var(--motored-danger, #c0392b)', fontSize: '0.75rem' }}>{accionError}</p>}

      {puedeEscribir && (
        <AccionesCarga
          estado={informe.estado} accionando={accionando} bloqueo={simulacion.bloqueo}
          onAplicar={handleAplicar} onAnular={handleAnular}
        />
      )}
    </div>
  );
}
