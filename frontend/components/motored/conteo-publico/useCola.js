/**
 * Flushes the device's offline queue (lib/motored/conteoCola.js): every
 * `intervaloMs` it sends the next batch (<= 100 readings) or void. A network
 * failure keeps everything and retries with backoff; `online` retries at
 * once. `beforeunload` warns while anything is pending.
 *
 * `eventos` (read through a ref, so they may change every render):
 * onHechos(items, referencias), onDesconocidos(items), onRechazadas([{item,
 * motivo}]), onAnulacionFallida(item, error), onSinUbicacion(),
 * onSesionPerdida().
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { esErrorDeRed } from '../../../lib/motored/conteoPublicoApi';
import {
  aPayload, aplicarRespuesta, guardarCola, leerCola, lecturasPendientes, quitarItem, retrasoReintento,
  siguienteEnvio,
} from '../../../lib/motored/conteoCola';

const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

function colaInicial(slug, sesionId) {
  const guardada = leerCola(slug);
  // A queue of another (closed) session belongs to another pair: never
  // send it under this one. The join screen already warned about it.
  return guardada.sesionId && guardada.sesionId !== sesionId ? [] : guardada.items;
}

export default function useCola({ slug, sesionId, api, intervaloMs, eventos }) {
  const ev = useRef(eventos);
  ev.current = eventos;
  const [items, setEstado] = useState(() => colaInicial(slug, sesionId));
  const itemsRef = useRef(items);
  const enVuelo = useRef(new Set());
  const enviando = useRef(false);
  // Paused until the screen seeded its totals, so a reading cannot be
  // counted both in the server summary and as a local pending one.
  const pausada = useRef(true);
  const fallos = useRef(0);
  const proximo = useRef(0);
  const [sinConexion, setSinConexion] = useState(
    typeof navigator !== 'undefined' && navigator.onLine === false,
  );

  const setItems = useCallback((cambio) => {
    const nuevos = cambio(itemsRef.current);
    itemsRef.current = nuevos;
    guardarCola(slug, { sesionId, items: nuevos });
    setEstado(nuevos);
  }, [slug, sesionId]);

  const encolar = useCallback((...nuevos) => setItems((xs) => [...xs, ...nuevos]), [setItems]);

  /** Drops an unsent reading; false when it is (being) sent already. */
  const quitarPendiente = useCallback((id) => {
    const esta = itemsRef.current.some((i) => i.op === 'lectura' && i.id === id);
    if (!esta || enVuelo.current.has(id)) return false;
    setItems((xs) => quitarItem(xs, id));
    return true;
  }, [setItems]);

  const fallar = useCallback((error) => {
    if (error.status === 401) {
      ev.current.onSesionPerdida();
    } else if (error.codigo === 'SIN_UBICACION') {
      pausada.current = true;
      ev.current.onSinUbicacion();
    } else {
      fallos.current += 1;
      proximo.current = Date.now() + retrasoReintento(fallos.current, intervaloMs);
      if (esErrorDeRed(error)) setSinConexion(true);
    }
  }, [intervaloMs]);

  const enviarAnulacion = useCallback(async (item) => {
    try {
      await api.anular(item.id);
    } catch (error) {
      if (esErrorDeRed(error) || error.status === 401 || error.codigo === 'SIN_UBICACION') throw error;
      ev.current.onAnulacionFallida(item, error);
    }
    setItems((xs) => quitarItem(xs, item.id, 'anular'));
  }, [api, setItems]);

  const enviarLote = useCallback(async (lote) => {
    const r = await api.enviarLecturas(lote.map(aPayload));
    const res = aplicarRespuesta(itemsRef.current, lote, r);
    setItems(() => res.items);
    if (res.hechos.length) ev.current.onHechos(res.hechos, r.referencias || {});
    if (res.desconocidos.length) ev.current.onDesconocidos(res.desconocidos);
    if (res.rechazadas.length) ev.current.onRechazadas(res.rechazadas);
  }, [api, setItems]);

  /** One request; true when it went through. */
  const paso = useCallback(async () => {
    const envio = siguienteEnvio(itemsRef.current);
    if (!envio || enviando.current) return false;
    enviando.current = true;
    envio.items.forEach((i) => enVuelo.current.add(i.id));
    try {
      if (envio.tipo === 'anular') await enviarAnulacion(envio.items[0]);
      else await enviarLote(envio.items);
      fallos.current = 0;
      proximo.current = 0;
      setSinConexion(false);
      return true;
    } catch (error) {
      fallar(error);
      return false;
    } finally {
      envio.items.forEach((i) => enVuelo.current.delete(i.id));
      enviando.current = false;
    }
  }, [enviarAnulacion, enviarLote, fallar]);

  useEffect(() => {
    const id = setInterval(() => {
      if (pausada.current || Date.now() < proximo.current) return;
      paso();
    }, intervaloMs);
    return () => clearInterval(id);
  }, [paso, intervaloMs]);

  useEffect(() => {
    const enLinea = () => {
      proximo.current = 0;
      // Paused while the screen seeds its list: sending now could count a
      // reading both in the server summary and as a local pending one.
      if (!pausada.current) paso();
    };
    const fuera = () => setSinConexion(true);
    window.addEventListener('online', enLinea);
    window.addEventListener('offline', fuera);
    return () => {
      window.removeEventListener('online', enLinea);
      window.removeEventListener('offline', fuera);
    };
  }, [paso]);

  const pendientes = lecturasPendientes(items);
  useEffect(() => {
    if (!items.length) return undefined;
    const avisar = (e) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', avisar);
    return () => window.removeEventListener('beforeunload', avisar);
  }, [items.length]);

  /**
   * Sends everything now (location change, finishing a task, leaving).
   * 'vacia' when nothing is left, 'sinUbicacion' when the server has no
   * location for this device, 'pendiente' otherwise (offline).
   */
  const vaciar = useCallback(async () => {
    pausada.current = false;
    for (let intento = 0; intento < 200 && itemsRef.current.length; intento += 1) {
      if (enviando.current) {
        await esperar(30);
      } else if (!(await paso())) {
        break;
      }
    }
    if (!itemsRef.current.length) return 'vacia';
    return pausada.current ? 'sinUbicacion' : 'pendiente';
  }, [paso]);

  const reanudar = useCallback(() => {
    pausada.current = false;
  }, []);

  /**
   * Stops sending and waits for a request already in flight, so a reseed
   * reads the queue and the server at the same point: a reading is then
   * either in the server's list or still queued, never lost between both.
   */
  const pausar = useCallback(async () => {
    pausada.current = true;
    for (let intento = 0; intento < 200 && enviando.current; intento += 1) {
      await esperar(30);
    }
  }, []);

  const itemsActuales = useCallback(() => itemsRef.current, []);

  return {
    items, pendientes, sinConexion, encolar, quitarPendiente, vaciar, reanudar, pausar, itemsActuales,
  };
}
