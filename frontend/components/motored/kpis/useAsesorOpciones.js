'use client';
/**
 * Options of the "Asesor" filter: the asesores of the chosen stores, loaded when the Asesores tab is active and
 * cached per store filter. Returns null until the list of THIS store filter has arrived (or if it failed).
 */
import { useEffect, useRef, useState } from 'react';
import { getAsesoresOpciones } from '../../../lib/motored/kpisApi';

export default function useAsesorOpciones(activo, sucursales) {
  const clave = [...sucursales].sort().join(',');
  const cache = useRef(new Map());
  const [estado, setEstado] = useState({ clave: null, lista: null });

  useEffect(() => {
    if (!activo) return undefined;
    if (cache.current.has(clave)) {
      setEstado({ clave, lista: cache.current.get(clave) });
      return undefined;
    }
    let vigente = true;
    getAsesoresOpciones(sucursales).then(
      (data) => {
        cache.current.set(clave, data.asesores);
        if (vigente) setEstado({ clave, lista: data.asesores });
      },
      () => { if (vigente) setEstado({ clave, lista: null }); },
    );
    return () => { vigente = false; };
    // `sucursales` is summarized by `clave`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activo, clave]);

  return estado.clave === clave ? estado.lista : null;
}
