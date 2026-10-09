/**
 * State of a joined device: session facts, the current location (location
 * first), reconteo tasks, the offline queue and the readings. Loads on
 * mount, refreshes the session state and tasks every 30 s, and returns
 * the actions the desktop and mobile screens share.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { crearConteoApi, esErrorDeRed } from '../../../lib/motored/conteoPublicoApi';
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
  const [ubicaciones, setUbicaciones] = useState([]);
  const [tareas, setTareas] = useState([]);
  const [tareaId, setTareaId] = useState(null);
  const [ocupado, setOcupado] = useState(false);
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
        fijarUbicacionLocal(actual);
        sembrar(rec, cola.itemsActuales(), actual && actual.codigo);
      } catch (error) {
        manejarError(error);
        if (vivo && esErrorDeRed(error)) sembrar(null, cola.itemsActuales(), ubicacion && ubicacion.codigo);
      }
      cola.reanudar();
      api.ubicaciones().then((u) => vivo && setUbicaciones(u || [])).catch(() => {});
    })();
    const id = setInterval(refrescar, REFRESCO_MS);
    return () => {
      vivo = false;
      clearInterval(id);
    };
    // Load once per device session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api]);

  const cambiarUbicacion = useCallback(async (codigo, nombre) => {
    setOcupado(true);
    try {
      const estadoCola = await cola.vaciar();
      if (estadoCola === 'pendiente') {
        lecturas.setAviso({ tipo: 'error', texto: TEXTOS.pendientesCambio });
        pitar('error');
        return false;
      }
      const r = await api.fijarUbicacion(codigo, nombre);
      const nueva = { codigo: r.ubicacion.codigo, nombre: r.ubicacion.nombre };
      fijarUbicacionLocal(nueva);
      cola.pausar();
      let rec = null;
      try {
        rec = await api.recientes();
      } catch (error) {
        manejarError(error);
      }
      sembrar(rec, cola.itemsActuales(), nueva.codigo);
      cola.reanudar();
      lecturas.setAviso(null);
      pitar('ok');
      return true;
    } catch (error) {
      manejarError(error);
      const texto = esErrorDeRed(error)
        ? 'Sin conexión: no se pudo cambiar la ubicación.'
        : (error.message || 'No se pudo cambiar la ubicación.');
      lecturas.setAviso({ tipo: 'error', texto });
      pitar('error');
      return false;
    } finally {
      setOcupado(false);
    }
  }, [api, cola, fijarUbicacionLocal, lecturas, manejarError, sembrar]);
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
    info, ubicacion, ubicaciones, tareas, tarea, ocupado, lecturas,
    pendientes: cola.pendientes, sinConexion: cola.sinConexion,
    cambiarUbicacion, elegirTarea: setTareaId, terminarTarea, salir,
  };
}
