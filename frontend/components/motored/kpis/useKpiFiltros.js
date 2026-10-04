'use client';
/** Filters of the KPI's: loads the options once and keeps months, stores and HMCL mode (default: year to date). */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { getOpciones } from '../../../lib/motored/kpisApi';
import { presetMeses } from './periodo';

const MENSAJE_ERROR = "No pudimos cargar los filtros de los KPI's. Intentá de nuevo en unos segundos.";

export default function useKpiFiltros(activo) {
  const [opciones, setOpciones] = useState(null);
  const [error, setError] = useState(null);
  const [cambios, setCambios] = useState({});

  useEffect(() => {
    if (!activo) return undefined;
    let vigente = true;
    getOpciones().then(
      (data) => { if (vigente) setOpciones(data); },
      () => { if (vigente) setError(MENSAJE_ERROR); },
    );
    return () => { vigente = false; };
  }, [activo]);

  const filtros = useMemo(() => ({
    meses: opciones?.ultimo_mes ? presetMeses('ytd', opciones.ultimo_mes) : null,
    sucursales: [],
    hmcl: 'incluir',
    ...cambios,
  }), [opciones, cambios]);
  const cambiar = useCallback((parcial) => setCambios((previo) => ({ ...previo, ...parcial })), []);
  return { opciones, filtros, cambiar, error };
}
