/**
 * State of a joined device: session facts, the current location (location
 * first), reconteo tasks, the offline queue and the readings. Loads on
 * mount, refreshes the session state and tasks every 30 s, and returns
 * the actions the desktop and mobile screens share.
 *
 * Changing location never waits for the network (WU13b): the new location
 * applies at once, marked `sinConfirmar`, and every later reading carries
 * it. `sincronizar` then sends the queue first, tells the server
 * (`PUT /ubicacion`, so the leader panel shows it) and reseeds the list;
 * offline it waits for the `online` event or the 30 s refresh. Sending the
 * queue before the PUT keeps older readings from moving the server's
 * current location back.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { crearConteoApi, esErrorDeRed } from '../../../lib/motored/conteoPublicoApi';
import { codigoUbicacion } from './registro';
import useCatalogo from './useCatalogo';
import useCola from './useCola';
import useLecturas from './useLecturas';
import { pitar } from './sonidos';
import { TEXTOS } from './textos';

const REFRESCO_MS = 30000;

export default function useConteo({ slug, sesion, intervaloEnvioMs, onSesionPerdida, onUbicacion }) {
  const api = useMemo(() => crearConteoApi(slug, sesion.token), [slug, sesion.token]);
  const [info, setInfo] = useState({ etiqueta: sesion.etiqueta, sucursal: sesion.sucursal, estado: null });
  const [ubicacion, setUbicacion] = useState(sesion.ubicacion || null);
  const ubicacionRef = useRef(ubicacion);
  const sincronizando = useRef(false);
  const sincronizarRef = useRef(() => {});
  const [ubicaciones, setUbicaciones] = useState([]);
  const [tareas, setTareas] = useState([]);
  const [tareaId, setTareaId] = useState(null);
  const buscar = useCatalogo(api);
  const puente = useRef({});
  const perdida = useRef(onSesionPerdida);
  perdida.current = onSesionPerdida;

  const manejarError = useCallback((error) => {
    if (error && error.status === 401) perdida.current();
  }, []);

  const cola = useCola({
    slug, sesionId: sesion.sesionId, api, intervaloMs: intervaloEnvioMs,
    eventos: {
      onHechos: (...a) => puente.current.onHechos(...a),
      onDesconocidos: (...a) => puente.current.onDesconocidos(...a),
      onRechazadas: (...a) => puente.current.onRechazadas(...a),
      onAnulacionFallida: (...a) => puente.current.onAnulacionFallida(...a),
      onSinUbicacion: () => {
        ubicacionRef.current = null;
        setUbicacion(null);
        puente.current.avisar({ tipo: 'sinUbicacion', texto: TEXTOS.sinUbicacion });
      },
      onSesionPerdida: () => perdida.current(),
    },
  });

  const tarea = tareas.find((t) => t.id === tareaId && t.estado === 'ASIGNADO') || null;
  const cambiarRef = useRef(null);
  const lecturas = useLecturas({
    cola, buscar, ubicacion, estado: info.estado, tarea,
    onEtiquetaUbicacion: (codigo) => cambiarRef.current(codigo),
  });
  puente.current = { ...lecturas.eventosCola, avisar: lecturas.setAviso };
  const { sembrar } = lecturas;

  const fijarUbicacionLocal = useCallback((nueva) => {
    ubicacionRef.current = nueva;
    setUbicacion(nueva);
    onUbicacion(nueva);
  }, [onUbicacion]);

  const refrescar = useCallback(async () => {
    try {
      const [s, t] = await Promise.all([api.sesion(), api.reconteos()]);
      setInfo({ etiqueta: s.etiqueta, sucursal: s.sucursal, estado: s.estado_conteo });
      setTareas(t || []);
    } catch (error) {
      manejarError(error);
    }
  }, [api, manejarError]);

  useEffect(() => {
    let vivo = true;
    (async () => {
      await refrescar();
      try {
        const rec = await api.recientes();
        if (!vivo) return;
        const actual = rec.ubicacion_actual
          ? { codigo: rec.ubicacion_actual.codigo, nombre: rec.ubicacion_actual.nombre } : null;
        sembrar(rec, cola.itemsActuales(), actual && actual.codigo);
        // A location changed offline and not told yet wins over the server's.
        const local = ubicacionRef.current;
        if (!local || !local.sinConfirmar) fijarUbicacionLocal(actual);
      } catch (error) {
        manejarError(error);
        const local = ubicacionRef.current;
        if (vivo && esErrorDeRed(error)) sembrar(null, cola.itemsActuales(), local && local.codigo);
      }
      cola.reanudar();
      if (vivo) sincronizarRef.current();
      api.ubicaciones().then((u) => vivo && setUbicaciones(u || [])).catch(() => {});
    })();
    const id = setInterval(() => {
      refrescar();
      sincronizarRef.current();
    }, REFRESCO_MS);
    const enLinea = () => sincronizarRef.current();
    window.addEventListener('online', enLinea);
    return () => {
      vivo = false;
      clearInterval(id);
      window.removeEventListener('online', enLinea);
    };
    // Load once per device session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api]);

  /** The server's current list of this location (after it was told). */
  const resembrarLista = useCallback(async (codigo) => {
    cola.pausar();
    try {
      const rec = await api.recientes();
      const actual = ubicacionRef.current;
      const delServidor = rec.ubicacion_actual && rec.ubicacion_actual.codigo;
      if (actual && actual.codigo === codigo && delServidor === codigo) {
        sembrar(rec, cola.itemsActuales(), codigo);
      }
    } catch (error) {
      manejarError(error);
    } finally {
      cola.reanudar();
    }
  }, [api, cola, manejarError, sembrar]);

  /** Tells the server one location; false when it must be retried. */
  const confirmar = useCallback(async (objetivo) => {
    let estado = await cola.vaciar();
    if (estado === 'sinUbicacion') {
      // Old readings without a stamp wait for the server to have a location.
      await api.fijarUbicacion(objetivo.codigo);
      estado = await cola.vaciar();
    }
    if (estado !== 'vacia') return false;
    const r = await api.fijarUbicacion(objetivo.codigo);
    if (ubicacionRef.current !== objetivo) return false;
    const nueva = { codigo: r.ubicacion.codigo, nombre: r.ubicacion.nombre };
    fijarUbicacionLocal(nueva);
    await resembrarLista(nueva.codigo);
    return true;
  }, [api, cola, fijarUbicacionLocal, resembrarLista]);

  const sincronizar = useCallback(async () => {
    const objetivo = ubicacionRef.current;
    if (!objetivo || !objetivo.sinConfirmar || sincronizando.current) return;
    sincronizando.current = true;
    let hecho = false;
    try {
      hecho = await confirmar(objetivo);
    } catch (error) {
      manejarError(error);
      if (!esErrorDeRed(error) && error.status !== 401 && ubicacionRef.current === objetivo) {
        fijarUbicacionLocal(null);
        lecturas.setAviso({ tipo: 'error', texto: error.message || 'No se pudo cambiar la ubicación.' });
        pitar('error');
      }
    } finally {
      sincronizando.current = false;
    }
    // Moved again while this one was being told: tell the newest.
    const ahora = ubicacionRef.current;
    if (!hecho && ahora !== objetivo && ahora && ahora.sinConfirmar) sincronizarRef.current();
  }, [confirmar, fijarUbicacionLocal, lecturas, manejarError]);
  sincronizarRef.current = sincronizar;

  /**
   * Applies at once, online or not (WU13b), and tells the server in the
   * background. Only an invalid code is refused here.
   */
  const cambiarUbicacion = useCallback(async (texto) => {
    const codigo = codigoUbicacion(texto);
    if (!codigo) {
      lecturas.setAviso({ tipo: 'error', texto: TEXTOS.ubicacionInvalida });
      pitar('error');
      return false;
    }
    const conocida = ubicaciones.find((u) => u.codigo === codigo);
    fijarUbicacionLocal({ codigo, nombre: conocida ? conocida.nombre : codigo, sinConfirmar: true });
    lecturas.setAviso(null);
    pitar('ok');
    sincronizar();
    return true;
  }, [fijarUbicacionLocal, lecturas, sincronizar, ubicaciones]);
  cambiarRef.current = cambiarUbicacion;

  const terminarTarea = useCallback(async (id) => {
    if ((await cola.vaciar()) === 'pendiente') {
      lecturas.setAviso({ tipo: 'error', texto: TEXTOS.pendientesTerminar });
      return false;
    }
    try {
      await api.terminarReconteo(id);
      setTareaId(null);
      await refrescar();
      return true;
    } catch (error) {
      manejarError(error);
      lecturas.setAviso({ tipo: 'error', texto: error.message || 'No se pudo terminar el reconteo.' });
      return false;
    }
  }, [api, cola, lecturas, manejarError, refrescar]);

  const salir = useCallback(async () => {
    if ((await cola.vaciar()) === 'pendiente') {
      lecturas.setAviso({ tipo: 'error', texto: TEXTOS.pendientesSalir });
      return false;
    }
    try {
      await api.salir();
    } catch (error) {
      if (esErrorDeRed(error)) {
        lecturas.setAviso({ tipo: 'error', texto: 'Sin conexión: no se pudo salir.' });
        return false;
      }
    }
    return true;
  }, [api, cola, lecturas]);

  return {
    // Changing location never waits for the network, so it is never busy.
    info, ubicacion, ubicaciones, tareas, tarea, ocupado: false, lecturas,
    pendientes: cola.pendientes, sinConexion: cola.sinConexion,
    cambiarUbicacion, elegirTarea: setTareaId, terminarTarea, salir,
  };
}
