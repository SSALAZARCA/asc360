'use client';
/**
 * The store's "Pendientes por sanear" of a PROGRAMADO conteo (WU15): reads
 * `/pendientes` once and marks / unmarks an item "Verificado en el ERP".
 * Both writes answer the refreshed list, which replaces the current one.
 */
import { useEffect, useState } from 'react';
import {
  desverificarPendiente, obtenerPendientesConteo, verificarPendiente,
} from '../../../lib/motored/conteosApi';

export default function usePendientesConteo(conteoId, activo) {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState('');
  const [ocupado, setOcupado] = useState('');

  useEffect(() => {
    if (!activo) return undefined;
    let vivo = true;
    Promise.resolve()
      .then(() => obtenerPendientesConteo(conteoId))
      .then((respuesta) => { if (vivo && respuesta) setDatos(respuesta); })
      .catch((err) => {
        if (vivo) setError(err.message || 'No se pudieron consultar los pendientes de la tienda.');
      });
    return () => { vivo = false; };
  }, [conteoId, activo]);

  /** Marks the item, or undoes the mark when `verificado` is already set. */
  const cambiar = async (tipo, fila) => {
    setOcupado(fila.clave);
    setError('');
    try {
      const accion = fila.verificado ? desverificarPendiente : verificarPendiente;
      setDatos(await accion(conteoId, tipo, fila.clave));
    } catch (err) {
      setError(err.message || 'No se pudo guardar la verificación.');
    } finally {
      setOcupado('');
    }
  };
  return { datos, error, ocupado, cambiar };
}
