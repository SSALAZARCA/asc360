'use client';
/**
 * State of the raw ERP VENTAS dry run of one carga: the live
 * `referencias-sin-linea` payload, the line options (`lineas_comerciales`,
 * or the seven defaults when it cannot be read) and the per-row and bulk
 * assignments. Nothing is requested while `activo` is false.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  asignarLineaReferencia, asignarLineasReferencias, getParametroVigente, getReferenciasSinLinea,
} from '../../../lib/motored/api';
import { mensajeAsignacion, opcionesDeLinea } from './ventasErp';

async function leerLineas() {
  try {
    const { valor } = await getParametroVigente('lineas_comerciales');
    return opcionesDeLinea(Array.isArray(valor) ? valor : []);
  } catch {
    return opcionesDeLinea([]);
  }
}

function useLineas(activo) {
  const [lineas, setLineas] = useState(() => opcionesDeLinea([]));
  useEffect(() => {
    if (activo) leerLineas().then(setLineas);
  }, [activo]);
  return lineas;
}

export default function useReferenciasSinLinea(cargaId, activo) {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState('');
  const [aviso, setAviso] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const lineas = useLineas(activo);

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

  /** Runs one assignment; on failure shows the message and re-reads the live list. */
  const asignar = async (llamada) => {
    setOcupado(true);
    setAviso('');
    try {
      setDatos(await llamada());
      return true;
    } catch (err) {
      setAviso(mensajeAsignacion(err));
      await recargar();
      return false;
    } finally {
      setOcupado(false);
    }
  };

  return {
    datos, error, aviso, ocupado, lineas, recargar,
    asignarUna: (referenciaId, linea) => asignar(() => asignarLineaReferencia(cargaId, referenciaId, linea)),
    asignarVarias: (asignaciones) => asignar(() => asignarLineasReferencias(cargaId, asignaciones)),
  };
}
