'use client';
/**
 * Data and actions of the live panel (WU12). One tick reads the
 * differences (always `todas`: the KPIs need every row; the filter buttons
 * work on that list) and the pairs. A new estado in the answer (round
 * ended, closed elsewhere) asks the container to reload the conteo.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import * as api from '../../../lib/motored/conteosApi';
import usePollingConteo from './usePollingConteo';

export default function usePanel(conteo, onCambioEstado) {
  const [diferencias, setDiferencias] = useState(null);
  const [sesiones, setSesiones] = useState([]);
  const [actualizado, setActualizado] = useState(null);
  const [aviso, setAviso] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const estadoRef = useRef(conteo.estado);
  estadoRef.current = conteo.estado;
  const id = conteo.id;

  const cargar = useCallback(async () => {
    try {
      const [dif, ses] = await Promise.all([api.obtenerDiferencias(id, 'todas'), api.listarSesiones(id)]);
      setDiferencias(dif);
      setSesiones(ses);
      setActualizado(Date.now());
      if (dif.estado && dif.estado !== estadoRef.current) onCambioEstado();
    } catch (err) {
      setAviso({ tipo: 'error', texto: err.message || 'No se pudo actualizar el panel.' });
    }
  }, [id, onCambioEstado]);

  useEffect(() => { cargar(); }, [cargar]);
  usePollingConteo(cargar, true);

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

  return { diferencias, sesiones, actualizado, aviso, ocupado, cargar, acciones };
}
