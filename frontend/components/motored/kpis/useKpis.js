'use client';
/**
 * Data of the active KPI's tab. Only the active tab is fetched, responses are cached in memory per
 * (tab, months, stores, hmcl) and a response that arrives after a newer request is discarded.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import * as kpisApi from '../../../lib/motored/kpisApi';

const MENSAJE_ERROR = "No pudimos cargar los KPI's. Intentá de nuevo en unos segundos.";
const API = { ventas: kpisApi.getVentas, tiendas: kpisApi.getTiendas, asesores: kpisApi.getAsesores };

export const claveKpis = (tab, { meses, sucursales = [], hmcl }) =>
  [tab, [...meses].sort().join(','), [...sucursales].sort().join(','), hmcl].join('|');

export default function useKpis(tab, filtros, api = API) {
  const cache = useRef(new Map());
  const pendientes = useRef(new Map());
  const solicitud = useRef(0);
  const fetcher = api[tab];
  const activo = Boolean(fetcher && filtros.meses?.length);
  const clave = activo ? claveKpis(tab, filtros) : null;
  const [estado, setEstado] = useState({ clave: null, data: null, error: null });
  const [version, setVersion] = useState(0);
  /** Drops every cached response and fetches the active tab again (after a summary rebuild). */
  const recargar = useCallback(() => {
    cache.current.clear();
    pendientes.current.clear();
    setVersion((v) => v + 1);
  }, []);

  useEffect(() => {
    if (!clave) return undefined;
    const numero = ++solicitud.current;
    if (cache.current.has(clave)) {
      setEstado({ clave, data: cache.current.get(clave), error: null });
      return undefined;
    }
    setEstado({ clave, data: null, error: null });
    // An identical request already in flight is reused instead of fired again.
    if (!pendientes.current.has(clave)) {
      const promesa = Promise.resolve(fetcher(filtros));
      pendientes.current.set(clave, promesa);
      const soltar = () => pendientes.current.delete(clave);
      promesa.then(soltar, soltar);
    }
    pendientes.current.get(clave).then(
      (data) => {
        cache.current.set(clave, data);
        if (numero === solicitud.current) setEstado({ clave, data, error: null });
      },
      () => { if (numero === solicitud.current) setEstado({ clave, data: null, error: MENSAJE_ERROR }); },
    );
    return undefined;
    // `filtros` is summarized by `clave`; the fetcher is stable per tab.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clave, version]);

  if (!clave) return { data: null, loading: false, error: null, recargar };
  if (estado.clave !== clave) return { data: cache.current.get(clave) ?? null, loading: !cache.current.has(clave), error: null, recargar };
  return { data: estado.data, loading: !estado.data && !estado.error, error: estado.error, recargar };
}
