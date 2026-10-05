'use client';
/** State of the "Nueva corrida" form: fecha de corte, tiendas, nota and the launch. */
import { useCallback, useState } from 'react';
import { crearCorrida } from '../../../lib/motored/pedidosApi';
import { listMaestros } from '../../../lib/motored/api';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';

export const MODO_TODAS = 'todas';
export const MODO_SELECCION = 'seleccion';

export function armarCuerpo({ fecha, modo, seleccion, nota, overrides }) {
  return {
    fecha_corte: fecha,
    ...(modo === MODO_SELECCION ? { sucursal_ids: seleccion } : {}),
    ...(nota.trim() ? { nota: nota.trim() } : {}),
    ...(overrides ? { overrides } : {}),
  };
}

/** `overrides` (optional) turns the launch into a scenario: only the parameters to test, as the server expects them. */
export default function useLanzarCorrida(onCreada, overrides) {
  const [fecha, setFecha] = useState('');
  const [modo, setModoEstado] = useState(MODO_TODAS);
  const [seleccion, setSeleccion] = useState([]);
  const [nota, setNota] = useState('');
  const [tiendas, setTiendas] = useState({ items: null, error: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [creada, setCreada] = useState(null);

  const cargarTiendas = useCallback(async () => {
    try {
      const todas = await listMaestros('sucursales');
      setTiendas({ items: todas.filter((s) => s.activa !== false && !s.principal_id), error: '' });
    } catch (fallo) {
      setTiendas({ items: null, error: mensajeConCodigo(fallo, 'No se pudo cargar las tiendas.') });
    }
  }, []);

  const setModo = useCallback((nuevo) => {
    setModoEstado(nuevo);
    if (nuevo === MODO_SELECCION && !tiendas.items) cargarTiendas();
  }, [tiendas.items, cargarTiendas]);

  const alternar = useCallback((id) => {
    setSeleccion((actual) => (actual.includes(id) ? actual.filter((x) => x !== id) : [...actual, id]));
  }, []);

  const lanzar = useCallback(async () => {
    const ordenadas = (tiendas.items || []).map((s) => s.id).filter((id) => seleccion.includes(id));
    setBusy(true);
    setError('');
    setCreada(null);
    try {
      const nueva = await crearCorrida(armarCuerpo({ fecha, modo, seleccion: ordenadas, nota, overrides }));
      setCreada(nueva);
      setNota('');
      onCreada?.(nueva);
    } catch (fallo) {
      setError(mensajeConCodigo(fallo, 'No se pudo crear la corrida.'));
    } finally {
      setBusy(false);
    }
  }, [fecha, modo, seleccion, nota, overrides, tiendas.items, onCreada]);

  const listo = fecha !== '' && !busy && (modo === MODO_TODAS || seleccion.length > 0);
  return {
    fecha, setFecha, modo, setModo, seleccion, alternar, nota, setNota,
    tiendas, busy, error, creada, listo, lanzar,
  };
}
