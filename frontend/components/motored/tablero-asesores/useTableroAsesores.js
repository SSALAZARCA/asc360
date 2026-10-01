'use client';
/**
 * Owns the filters (month range + HMCL mode) and the load of the "Tablero de
 * asesores". An invalid range is explained locally and never sent; a response
 * that arrives after a newer request was made is ignored.
 */
import { useEffect, useRef, useState } from 'react';
import { obtenerTablero } from './tableroApi';
import { rangoPorDefecto, validarRango } from './rango';

export default function useTableroAsesores(enabled) {
  const [filtros, setFiltros] = useState(() => ({ ...rangoPorDefecto(), hmcl: 'incluir' }));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const pedido = useRef(0);

  const errorDeRango = validarRango(filtros.desde, filtros.hasta);

  useEffect(() => {
    if (!enabled || errorDeRango) return undefined;
    const actual = ++pedido.current;
    setLoading(true);
    setError('');
    obtenerTablero(filtros)
      .then((resultado) => {
        if (actual === pedido.current) setData(resultado);
      })
      .catch((err) => {
        if (actual === pedido.current) setError(err.message || 'No se pudo cargar el tablero');
      })
      .finally(() => {
        if (actual === pedido.current) setLoading(false);
      });
    return () => { pedido.current += 1; };
  }, [enabled, errorDeRango, filtros.desde, filtros.hasta, filtros.hmcl]);

  return { filtros, setFiltros, data, loading, error: errorDeRango || error };
}
