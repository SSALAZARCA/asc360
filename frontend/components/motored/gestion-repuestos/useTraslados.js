'use client';
import { useCallback, useEffect, useState } from 'react';
import { confirmarTraslado, getTrasladosDetalle } from '../../../lib/motored/gestionRepuestosApi';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';

const MSG_CARGA = 'No se pudo cargar el seguimiento de traslados.';
const mismo = (a, b) => a.documento === b.documento && a.bodega_salida === b.bodega_salida;

/** Loads the whole pending list once (filters are applied in memory) and reloads it after a confirmation. */
export default function useTraslados() {
  const [ultimaCarga, setUltimaCarga] = useState(undefined); // undefined = loading, null = no traslados loaded
  const [items, setItems] = useState([]);
  const [ocupada, setOcupada] = useState(false);
  const [error, setError] = useState(null);

  const cargar = useCallback(async () => {
    const r = await getTrasladosDetalle();
    setUltimaCarga(r.ultima_carga ?? null);
    setItems(r.items || []);
  }, []);

  useEffect(() => {
    let vigente = true;
    cargar().catch(() => { if (vigente) setError(MSG_CARGA); });
    return () => { vigente = false; };
  }, [cargar]);

  const confirmar = async (item, estado) => {
    setOcupada(true);
    setError(null);
    try {
      const nuevo = await confirmarTraslado({ documento: item.documento, bodega_salida: item.bodega_salida, estado });
      setItems((lista) => lista.map((i) => (mismo(i, item) ? { ...i, ...nuevo } : i)));
      // The confirmation is already saved and shown; a failed reload only leaves the previous numbers.
      cargar().catch(() => {});
    } catch (e) {
      setError(mensajeConCodigo(e, 'No se pudo guardar la confirmación.'));
    } finally {
      setOcupada(false);
    }
  };

  return { ultimaCarga, items, error, ocupada, confirmar };
}
