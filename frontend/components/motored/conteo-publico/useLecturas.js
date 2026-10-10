/**
 * Readings of the pair: a scan is checked (location first, `UBI-` labels,
 * reconteo task, catalogue), queued with a client id, shown and beeped at
 * once. Each reading is stamped with the location in effect at scan time
 * (WU13b), so "Contado en <ubicación>" stays right after moving shelves
 * offline. Quantity edits are voids plus new readings (the API refuses
 * quantities <= 0). See `registro.js` for how the shown totals are kept.
 */
import { useCallback, useEffect, useState } from 'react';
import { nuevoId } from '../../../lib/motored/conteoCola';
import {
  baseDesde, candidatosAnular, esEtiquetaUbicacion, normalizar, planReduccion, resembrar,
  resumenUbicacion, totalDe,
} from './registro';
import { pitar, vibrar } from './sonidos';
import { TEXTOS, textoAmbiguo, textoMotivo } from './textos';

export default function useLecturas({ cola, buscar, ubicacion, estado, tarea, onEtiquetaUbicacion }) {
  const [bases, setBases] = useState({});
  const [registro, setRegistro] = useState([]);
  const [ultima, setUltima] = useState(null);
  const [aviso, setAviso] = useState(null);
  const [rechazos, setRechazos] = useState([]);
  const ubic = ubicacion ? ubicacion.codigo : null;
  const base = (ubic && bases[ubic]) || {};

  useEffect(() => {
    setUltima(null);
  }, [ubic]);

  /** Seeds one location from `recientes` (null offline) plus the queue. */
  const sembrar = useCallback((recientes, items, ubicacionCodigo) => {
    if (ubicacionCodigo) {
      const nueva = baseDesde(recientes ? recientes.resumen_ubicacion : []);
      setBases((b) => ({ ...b, [ubicacionCodigo]: nueva }));
    }
    setRegistro((r) => resembrar(r, recientes, items, ubicacionCodigo));
  }, []);

  const error = useCallback((nuevoAviso) => {
    setAviso(nuevoAviso);
    pitar('error');
  }, []);

  const agregar = useCallback((codigo, cantidad, metodo, { reconteoId = null, forzar = false, descripcion = '' } = {}) => {
    const item = {
      op: 'lectura', id: nuevoId(), codigo_leido: codigo, cantidad, leida_en: new Date().toISOString(),
      metodo, forzar_desconocido: forzar, reconteo_id: reconteoId, ubicacion_codigo: ubic, ubicacion: ubic,
      descripcion,
    };
    cola.encolar(item);
    setRegistro((r) => [...r, {
      id: item.id, codigo, descripcion, cantidad, ubicacion: ubic, reconteoId, origen: 'local', anulada: false,
    }]);
    setUltima({ codigo, descripcion, reconteoId, forzar, en: Date.now() });
    setAviso(null);
    pitar('ok');
    vibrar();
  }, [cola, ubic]);

  const registrarCodigo = useCallback((texto, metodo) => {
    const codigo = normalizar(texto);
    if (!codigo) return;
    if (esEtiquetaUbicacion(codigo)) {
      onEtiquetaUbicacion(codigo);
      return;
    }
    if (!ubic) {
      error({ tipo: 'sinUbicacion', texto: TEXTOS.sinUbicacion });
      return;
    }
    if (!tarea && estado === 'EN_RECONTEO') {
      error({ tipo: 'error', texto: TEXTOS.rondaTerminada });
      return;
    }
    // The catalogue answers with the MASTER code, so a label without the
    // master's hyphens is counted under the master code.
    const referencia = buscar(codigo);
    if (referencia && referencia.ambiguo) {
      error({ tipo: 'ambiguo', texto: textoAmbiguo(referencia.ambiguo) });
      return;
    }
    const enMaestro = referencia ? referencia.codigo : codigo;
    if (tarea) {
      if (enMaestro !== normalizar(tarea.codigo)) {
        error({ tipo: 'error', texto: `Este código no es el del reconteo activo (${tarea.codigo}). No se sumó nada.` });
        return;
      }
      agregar(enMaestro, 1, metodo, { reconteoId: tarea.id, descripcion: tarea.descripcion || '' });
      return;
    }
    if (referencia === null) {
      error({ tipo: 'desconocido', codigo, metodo });
      return;
    }
    agregar(enMaestro, 1, metodo, { descripcion: referencia ? referencia.nombre : '' });
  }, [agregar, buscar, error, estado, onEtiquetaUbicacion, tarea, ubic]);

  const forzarDesconocido = useCallback(() => {
    if (!aviso || aviso.tipo !== 'desconocido' || !ubic) return;
    agregar(aviso.codigo, 1, aviso.metodo || 'MANUAL', { forzar: true });
  }, [agregar, aviso, ubic]);

  const anularEntrada = useCallback((entrada) => {
    if (entrada.origen === 'local' && cola.quitarPendiente(entrada.id)) {
      setRegistro((r) => r.filter((x) => x.id !== entrada.id));
      return;
    }
    cola.encolar({
      op: 'anular', id: entrada.id, codigo: entrada.codigo, cantidad: entrada.cantidad, ubicacion: entrada.ubicacion,
    });
    setRegistro((r) => r.map((x) => (x.id === entrada.id ? { ...x, anulada: true } : x)));
  }, [cola]);

  const total = ultima ? totalDe(base, registro, ubic, ultima.codigo, ultima.reconteoId) : 0;

  const ajustar = useCallback((nuevo) => {
    if (!ultima || !ubic) return;
    const meta = Math.max(0, Math.round(Number(nuevo) || 0));
    const opciones = { reconteoId: ultima.reconteoId, forzar: ultima.forzar, descripcion: ultima.descripcion };
    if (meta > total) {
      agregar(ultima.codigo, meta - total, 'MANUAL', opciones);
      return;
    }
    if (meta === total) return;
    const candidatos = candidatosAnular(registro, ubic, ultima.codigo, ultima.reconteoId);
    const plan = planReduccion(candidatos, total - meta);
    plan.anular.forEach(anularEntrada);
    if (plan.reponer > 0) agregar(ultima.codigo, plan.reponer, 'MANUAL', opciones);
    else setUltima((u) => ({ ...u, en: Date.now() }));
  }, [agregar, anularEntrada, registro, total, ubic, ultima]);

  const seleccionar = useCallback((fila) => {
    setUltima({
      codigo: fila.codigo, descripcion: fila.descripcion, reconteoId: null,
      forzar: buscar(fila.codigo) === null, en: Date.now(),
    });
  }, [buscar]);

  const eventosCola = {
    onHechos: (hechos, referencias) => {
      const nombres = referencias || {};
      if (!Object.keys(nombres).length) return;
      setRegistro((r) => r.map((x) => (!x.descripcion && nombres[x.codigo]
        ? { ...x, descripcion: nombres[x.codigo] } : x)));
      setUltima((u) => (u && !u.descripcion && nombres[u.codigo] ? { ...u, descripcion: nombres[u.codigo] } : u));
    },
    onDesconocidos: (items) => {
      const ids = new Set(items.map((i) => i.id));
      setRegistro((r) => r.filter((x) => !ids.has(x.id)));
      const ultimo = items[items.length - 1];
      error({ tipo: 'desconocido', codigo: ultimo.codigo_leido, metodo: ultimo.metodo });
    },
    onRechazadas: (lista) => {
      const ids = new Set(lista.map((x) => x.item.id));
      setRegistro((r) => r.filter((x) => !ids.has(x.id)));
      setRechazos((prev) => [...lista.map(({ item, motivo }) => ({
        id: item.id, codigo: item.codigo_leido, texto: textoMotivo(motivo),
      })), ...prev].slice(0, 5));
      pitar('error');
    },
    onAnulacionFallida: (item, fallo) => {
      setRegistro((r) => r.map((x) => (x.id === item.id ? { ...x, anulada: false } : x)));
      setRechazos((prev) => [{ id: `${item.id}-anular`, codigo: item.codigo, texto: textoMotivo(fallo.codigo) },
        ...prev].slice(0, 5));
    },
  };

  return {
    filas: ubic ? resumenUbicacion(base, registro, ubic) : [],
    ultima, total, aviso, rechazos,
    setAviso, sembrar, registrarCodigo, forzarDesconocido, ajustar, seleccionar, eventosCola,
  };
}
