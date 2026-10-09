'use client';
/** Lazy per-carga detail: fetches when mounted and again whenever the quick filter changes. */
import { useEffect, useState } from 'react';
import { getDetalleCargaEncuesta } from '../../../lib/motored/encuestaCargasApi';

export default function useDetalleCarga(cargaId) {
  const [filtro, setFiltro] = useState('todas');
  const [filas, setFilas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let vigente = true;
    setLoading(true);
    setError('');
    getDetalleCargaEncuesta(cargaId, filtro)
      .then((data) => { if (vigente) setFilas(data); })
      .catch((err) => { if (vigente) setError(err.message || 'No se pudo cargar el detalle.'); })
      .finally(() => { if (vigente) setLoading(false); });
    return () => { vigente = false; };
  }, [cargaId, filtro]);

  return { filtro, setFiltro, filas, loading, error };
}
