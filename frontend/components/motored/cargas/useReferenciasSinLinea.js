'use client';
/**
 * State of the raw ERP VENTAS dry run of one carga: the live
 * `referencias-sin-linea` payload, the line options it carries
 * (`opciones_linea`, see `opcionesDeLinea`) and the per-row and bulk
 * assignments. Nothing is requested while `activo` is false.
 */
import { useCallback, useEffect, useState } from 'react';
import { asignarLineaReferencia, asignarLineasReferencias, getReferenciasSinLinea } from '../../../lib/motored/api';
import { mensajeAsignacion, opcionesDeLinea } from './ventasErp';

export default function useReferenciasSinLinea(cargaId, activo) {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState('');
  const [aviso, setAviso] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const lineas = opcionesDeLinea(datos?.opciones_linea);

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
