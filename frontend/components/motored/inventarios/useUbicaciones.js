'use client';
/** The store's locations of a conteo (WU11): list, add, rename and (de)activate, reloading after each write. */
import { useCallback, useEffect, useState } from 'react';
import { crearUbicacion, editarUbicacion, listarUbicaciones } from '../../../lib/motored/conteosApi';

export default function useUbicaciones(conteoId) {
  const [lista, setLista] = useState([]);
  const [error, setError] = useState('');
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setLista(await listarUbicaciones(conteoId));
    } catch (err) {
      setError(err.message || 'No se pudieron cargar las ubicaciones.');
    }
  }, [conteoId]);

  useEffect(() => { cargar(); }, [cargar]);

  const escribir = async (accion) => {
    setOcupado(true);
    setError('');
    try {
      await accion();
      await cargar();
      return true;
    } catch (err) {
      setError(err.message || 'No se pudo guardar la ubicación.');
      return false;
    } finally {
      setOcupado(false);
    }
  };

  return {
    lista, error, ocupado,
    crear: (payload) => escribir(() => crearUbicacion(conteoId, payload)),
    renombrar: (id, nombre) => escribir(() => editarUbicacion(conteoId, id, { nombre })),
    activar: (id, activa) => escribir(() => editarUbicacion(conteoId, id, { activa })),
  };
}
