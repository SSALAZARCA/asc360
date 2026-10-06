'use client';
/**
 * Options of the "Asesor" filter: who sold with the active period, stores and HMCL (most sales first), loaded when
 * the Asesores tab is active and cached per filter. Returns null until the list of THESE filters has arrived (or if it failed).
 */
import { useEffect, useRef, useState } from 'react';
import { getAsesoresOpciones } from '../../../lib/motored/kpisApi';

const claveDe = ({ meses, sucursales = [], hmcl }) => [[...(meses ?? [])].sort().join(','), [...sucursales].sort().join(','), hmcl].join('|');

export default function useAsesorOpciones(activo, filtros) {
  const clave = claveDe(filtros);
  const listo = Boolean(activo && filtros.meses?.length);
  const cache = useRef(new Map());
  const [estado, setEstado] = useState({ clave: null, lista: null });

  useEffect(() => {
    if (!listo) return undefined;
    if (cache.current.has(clave)) {
      setEstado({ clave, lista: cache.current.get(clave) });
      return undefined;
    }
    let vigente = true;
    getAsesoresOpciones(filtros).then(
      (data) => {
        cache.current.set(clave, data.asesores);
        if (vigente) setEstado({ clave, lista: data.asesores });
      },
      () => { if (vigente) setEstado({ clave, lista: null }); },
    );
    return () => { vigente = false; };
    // `filtros` is summarized by `clave`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listo, clave]);

  return listo && estado.clave === clave ? estado.lista : null;
}
