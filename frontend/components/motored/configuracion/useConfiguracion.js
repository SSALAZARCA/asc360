'use client';
/** Reads the whole configuration (every key by section and group); `recargar` reads it again. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { getConfiguracion } from '../../../lib/motored/configuracionApi';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';

export default function useConfiguracion(habilitado) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [nonce, setNonce] = useState(0);
  const requestId = useRef(0);
  const recargar = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!habilitado) return;
    const id = ++requestId.current;
    setError('');
    getConfiguracion()
      .then((body) => { if (id === requestId.current) setData(body); })
      .catch((err) => { if (id === requestId.current) setError(mensajeConCodigo(err, 'No se pudo cargar la configuración.')); });
  }, [habilitado, nonce]);

  return { data, error, recargar };
}
