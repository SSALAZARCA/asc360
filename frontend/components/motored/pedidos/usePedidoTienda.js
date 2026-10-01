'use client';
/** Loads the header of one tienda pedido (state, totals, last event, envio). */
import { useCallback, useEffect, useRef, useState } from 'react';
import { getPedidoTienda } from '../../../lib/motored/pedidosApi';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';

export default function usePedidoTienda(corridaId, sucursalId, enabled) {
  const [cabecera, setCabecera] = useState(null);
  const [error, setError] = useState('');
  const [nonce, setNonce] = useState(0);
  const requestId = useRef(0);
  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!enabled) return;
    const id = ++requestId.current;
    setError('');
    getPedidoTienda(corridaId, sucursalId)
      .then((body) => { if (id === requestId.current) setCabecera(body); })
      .catch((err) => { if (id === requestId.current) setError(mensajeConCodigo(err, 'No se pudo cargar el pedido de la tienda.')); });
  }, [enabled, corridaId, sucursalId, nonce]);

  return { cabecera, error, reload };
}
