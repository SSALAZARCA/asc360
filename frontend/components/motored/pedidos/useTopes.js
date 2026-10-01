'use client';
/** Reads the budget cap screen data: the switch and the cap of every active tienda. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { getTopesPresupuesto } from '../../../lib/motored/pedidosApi';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';

export default function useTopes(habilitado) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [nonce, setNonce] = useState(0);
  const requestId = useRef(0);
  const recargar = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!habilitado) return;
    const id = ++requestId.current;
    setError('');
    getTopesPresupuesto()
      .then((body) => { if (id === requestId.current) setData(body); })
      .catch((err) => { if (id === requestId.current) setError(mensajeConCodigo(err, 'No se pudo cargar los topes.')); });
  }, [habilitado, nonce]);

  return { data, error, recargar };
}
