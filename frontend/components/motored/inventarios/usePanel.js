'use client';
/**
 * Data and actions of the live panel (WU12/WU12b). Every poll asks
 * `/panel` with the last version: `sin_cambios` only refreshes the clock
 * (and the idle-pair minutes); a new version brings the progress, partial
 * accuracy and per-pair readings, and only then are the differences
 * (always `todas`: the filter buttons work on that list) and the pairs
 * reloaded. "Actualizar ahora" and every write force a full reload. A new
 * estado (round ended, closed elsewhere) asks the container to reload.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as api from '../../../lib/motored/conteosApi';
import { unirParejas } from './conteosFormato';
import usePollingConteo from './usePollingConteo';

export default function usePanel(conteo, onCambioEstado) {
  const [vivo, setVivo] = useState(null);
  const [diferencias, setDiferencias] = useState(null);
  const [sesiones, setSesiones] = useState([]);
  const [actualizado, setActualizado] = useState(null);
  const [aviso, setAviso] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const estadoRef = useRef(conteo.estado);
  estadoRef.current = conteo.estado;
  // The version of the data on screen; set only after a full reload succeeded.
  const versionRef = useRef(undefined);
  const id = conteo.id;

  const leer = useCallback(async (forzar) => {
    try {
      const panel = await api.obtenerPanel(id, forzar ? undefined : versionRef.current);
      if (!panel.sin_cambios) {
        const [dif, ses] = await Promise.all([api.obtenerDiferencias(id, 'todas'), api.listarSesiones(id)]);
        setVivo(panel);
        setDiferencias(dif);
        setSesiones(ses);
        versionRef.current = panel.version;
        if (panel.estado && panel.estado !== estadoRef.current) onCambioEstado();
      }
      setActualizado(Date.now());
    } catch (err) {
      setAviso({ tipo: 'error', texto: err.message || 'No se pudo actualizar el panel.' });
    }
  }, [id, onCambioEstado]);
  const cargar = useCallback(() => leer(true), [leer]);
  const sondear = useCallback(() => leer(false), [leer]);

  useEffect(() => { cargar(); }, [cargar]);
  usePollingConteo(sondear, true);
  const parejas = useMemo(() => unirParejas(sesiones, vivo?.parejas), [sesiones, vivo]);

  /** Runs a write, shows its error, reloads; returns the answer (undefined on error). */
  const ejecutar = async (accion, { info, cambiaEstado = false } = {}) => {
    setOcupado(true);
    setAviso(null);
    try {
      const salida = await accion();
      if (info) setAviso({ tipo: 'info', texto: info(salida) });
      if (cambiaEstado) onCambioEstado();
      await cargar();
      return salida ?? true;
    } catch (err) {
      setAviso({ tipo: 'error', texto: err.message || 'No se pudo completar la acción.' });
      return undefined;
    } finally {
      setOcupado(false);
    }
  };

  const acciones = {
    pedirReconteo: (codigo) => ejecutar(() => api.pedirReconteo(id, codigo)),
    cancelarReconteo: (rid) => ejecutar(() => api.cancelarReconteo(id, rid)),
    repartir: () => ejecutar(() => api.repartirReconteos(id), {
      info: (r) => `${r.asignados.length} reconteos asignados${r.sin_pareja.length ? `; ${r.sin_pareja.length} sin pareja disponible` : ''}.`,
    }),
    desconectar: (sid) => ejecutar(() => api.desconectarSesion(id, sid)),
    terminarRonda: () => ejecutar(() => api.terminarRonda(id), {
      info: (r) => `Primera vuelta terminada: ${r.diferencias} diferencias y ${r.reconteos_creados} reconteos creados.`,
      cambiaEstado: true,
    }),
    descargarAvance: () => ejecutar(() => api.descargarAvance(id)),
  };

  return { vivo, diferencias, sesiones: parejas, actualizado, aviso, ocupado, cargar, acciones };
}
