'use client';
/**
 * State of the raw ERP VENTAS dry run of one carga: the live
 * `referencias-sin-linea` payload, the line options it carries
 * (`opciones_linea`, see `opcionesDeLinea`) and the pending line choices.
 * Picking a line (per row or for the checked rows) only records it locally;
 * `guardar` sends every pending choice in ONE bulk PUT, because each write
 * marks the KPI summary dirty. Nothing is requested while `activo` is false.
 */
import { useCallback, useEffect, useState } from 'react';
import { asignarLineasReferencias, getReferenciasSinLinea } from '../../../lib/motored/api';
import { mensajeAsignacion, opcionesDeLinea, ordenarSinLinea } from './ventasErp';

/** Pending `{ referencia_id: linea }`, limited to the refs still in `filas`. */
function usePendientes(filas) {
  const [elegidas, setElegidas] = useState({});
  const ids = (filas || []).map((f) => f.referencia_id);
  const pendientes = Object.fromEntries(Object.entries(elegidas).filter(([id]) => ids.includes(id)));
  const elegir = (referenciaIds, linea) => setElegidas((previas) => {
    const siguientes = { ...previas };
    referenciaIds.forEach((id) => {
      if (linea) siguientes[id] = linea;
      else delete siguientes[id];
    });
    return siguientes;
  });
  return { pendientes, elegir, limpiar: () => setElegidas({}) };
}

/** Asks the browser to confirm leaving the page while choices are unsaved. */
function useAvisoAlSalir(hayPendientes) {
  useEffect(() => {
    if (!hayPendientes) return undefined;
    const avisar = (e) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', avisar);
    return () => window.removeEventListener('beforeunload', avisar);
  }, [hayPendientes]);
}

export default function useReferenciasSinLinea(cargaId, activo) {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState('');
  const [aviso, setAviso] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const lineas = opcionesDeLinea(datos?.opciones_linea);
  const { pendientes, elegir, limpiar } = usePendientes(datos?.sin_linea);
  const cantidadPendientes = Object.keys(pendientes).length;
  useAvisoAlSalir(cantidadPendientes > 0);

  const recargar = useCallback(async () => {
    setError('');
    try {
      setDatos(await getReferenciasSinLinea(cargaId));
    } catch (err) {
      setError(`No se pudo revisar las referencias sin línea: ${err.message || 'error desconocido'}`);
    }
  }, [cargaId]);

  useEffect(() => {
    if (activo) recargar();
  }, [activo, recargar]);

  /** One bulk PUT with every pending choice; on failure the choices stay for the user to fix. */
  const guardar = async () => {
    const asignaciones = ordenarSinLinea(datos?.sin_linea)
      .filter((f) => pendientes[f.referencia_id])
      .map((f) => ({ referencia_id: f.referencia_id, linea_comercial: pendientes[f.referencia_id] }));
    if (!asignaciones.length) return;
    setOcupado(true);
    setAviso('');
    try {
      setDatos(await asignarLineasReferencias(cargaId, asignaciones));
      limpiar();
    } catch (err) {
      setAviso(mensajeAsignacion(err));
      await recargar();
    } finally {
      setOcupado(false);
    }
  };

  return { datos, error, aviso, ocupado, lineas, recargar, pendientes, cantidadPendientes, elegir, guardar };
}
