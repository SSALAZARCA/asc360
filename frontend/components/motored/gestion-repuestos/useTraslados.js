'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { confirmarTraslado, getTrasladosDetalle } from '../../../lib/motored/gestionRepuestosApi';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';

const MSG_CARGA = 'No se pudo cargar el seguimiento de traslados.';
const mismo = (a, b) => (
  a.documento === b.documento && a.bodega_salida === b.bodega_salida && a.bodega_entrada === b.bodega_entrada
);

/**
 * Loads the whole pending list (filters are applied in memory) and reloads it after a confirmation. Only the newest
 * request may write the state, and nothing is written once the panel is gone.
 */
function useCargaVigente() {
  const [ultimaCarga, setUltimaCarga] = useState(undefined); // undefined = loading, null = no traslados loaded
  const [filasConError, setFilasConError] = useState(0);
  const [items, setItems] = useState([]);
  const secuencia = useRef(0);
  const montado = useRef(true);
  useEffect(() => {
    montado.current = true;
    return () => { montado.current = false; };
  }, []);

  const cargar = useCallback(async () => {
    const mia = ++secuencia.current;
    const r = await getTrasladosDetalle();
    if (!montado.current || mia !== secuencia.current) return;
    setUltimaCarga(r.ultima_carga ?? null);
    setFilasConError(r.filas_con_error ?? 0);
    setItems(r.items || []);
  }, []);
  return { ultimaCarga, filasConError, items, setItems, cargar };
}

export default function useTraslados() {
  const { ultimaCarga, filasConError, items, setItems, cargar } = useCargaVigente();
  const [ocupada, setOcupada] = useState(false);
  const [error, setError] = useState(null);

  const cargarInicial = useCallback(() => {
    setError(null);
    cargar().catch(() => setError(MSG_CARGA));
  }, [cargar]);

  useEffect(() => { cargarInicial(); }, [cargarInicial]);

  const confirmar = async (item, estado) => {
    setOcupada(true);
    setError(null);
    try {
      const nuevo = await confirmarTraslado({
        documento: item.documento, bodega_salida: item.bodega_salida, bodega_entrada: item.bodega_entrada, estado,
      });
      setItems((lista) => lista.map((i) => (mismo(i, item) ? { ...i, ...nuevo } : i)));
      // The confirmation is already saved and shown; a failed reload only leaves the previous numbers.
      cargar().catch(() => {});
    } catch (e) {
      setError(mensajeConCodigo(e, 'No se pudo guardar la confirmación.'));
    } finally {
      setOcupada(false);
    }
  };

  const falloInicial = ultimaCarga === undefined && error !== null;
  return { ultimaCarga, filasConError, items, error, falloInicial, ocupada, confirmar, reintentar: cargarInicial };
}
