'use client';
/**
 * State of the scenario launcher: the catalog of engine keys, the keys the
 * user picked (each with the value in force, read only when the key is picked:
 * one call per picked key, never one per key of the catalog), what the user
 * typed, and the launch (the corrida fields come from `useLanzarCorrida`).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { getParametroVigente, listarClavesMotor } from '../../../lib/motored/pedidosApi';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';
import useLanzarCorrida from './useLanzarCorrida';
import { armarOverrides, borradorDesde } from './escenario';

export const LEYENDO = 'leyendo';
export const VIGENTE = 'vigente';
export const POR_DEFECTO = 'defecto';
export const NO_LEIDO = 'no-leido';

function useCatalogo() {
  const [catalogo, setCatalogo] = useState({ items: null, error: '' });
  useEffect(() => {
    let vivo = true;
    listarClavesMotor()
      .then((items) => { if (vivo) setCatalogo({ items, error: '' }); })
      .catch((fallo) => {
        if (vivo) setCatalogo({ items: null, error: mensajeConCodigo(fallo, 'No se pudo cargar los parámetros del cálculo.') });
      });
    return () => { vivo = false; };
  }, []);
  return catalogo;
}

/** The value in force of a key; a key without a version (404) or a failed read falls back to its default. */
async function leerActual(entrada) {
  try {
    const { valor } = await getParametroVigente(entrada.clave);
    return { actual: valor, fuente: VIGENTE };
  } catch (fallo) {
    return { actual: entrada.default, fuente: fallo.status === 404 ? POR_DEFECTO : NO_LEIDO };
  }
}

const filaNueva = (entrada) => ({
  clave: entrada.clave, tipo: entrada.tipo, opciones: entrada.opciones || [], actual: entrada.default,
  fuente: LEYENDO, borrador: borradorDesde(entrada.tipo, entrada.default),
});

function useFilas(catalogo) {
  const [filas, setFilas] = useState([]);

  const agregar = useCallback((clave) => {
    const entrada = (catalogo.items || []).find((e) => e.clave === clave);
    if (!entrada) return;
    setFilas((actuales) => (actuales.some((f) => f.clave === clave) ? actuales : [...actuales, filaNueva(entrada)]));
    leerActual(entrada).then(({ actual, fuente }) => {
      setFilas((actuales) => actuales.map((f) => (
        f.clave === clave && f.fuente === LEYENDO ? { ...f, actual, fuente, borrador: borradorDesde(f.tipo, actual) } : f
      )));
    });
  }, [catalogo.items]);

  const cambiar = useCallback((clave, borrador) => {
    setFilas((actuales) => actuales.map((f) => (f.clave === clave ? { ...f, borrador } : f)));
  }, []);
  const quitar = useCallback((clave) => setFilas((actuales) => actuales.filter((f) => f.clave !== clave)), []);
  return { filas, agregar, cambiar, quitar };
}

export default function useEscenario(onCreada) {
  const catalogo = useCatalogo();
  const { filas, agregar, cambiar, quitar } = useFilas(catalogo);
  const leidas = useMemo(() => filas.filter((f) => f.fuente !== LEYENDO), [filas]);
  const { overrides, errores, cambios } = useMemo(() => armarOverrides(leidas), [leidas]);
  const lanzar = useLanzarCorrida(onCreada, cambios > 0 ? overrides : undefined);
  const disponibles = (catalogo.items || []).filter((e) => !filas.some((f) => f.clave === e.clave));
  const listo = lanzar.listo && cambios > 0 && Object.keys(errores).length === 0 && leidas.length === filas.length;
  return { catalogo, disponibles, filas, errores, cambios, listo, agregar, cambiar, quitar, lanzar };
}
