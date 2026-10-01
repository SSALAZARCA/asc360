'use client';
/**
 * Cap data of ONE tienda pedido. A draft reads its recorte proposal (cap,
 * value, excess, the lines to cut and the `token`); a closed or sent pedido
 * reads its row of the corrida cap summary (the proposal is only for drafts).
 * Anything else (scenario, tienda without pedido) reads nothing. A failed
 * read hides the banner: the cap is advisory and must never break the page.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { getRecorte, getTopesCorrida } from '../../../lib/motored/pedidosApi';

const CERRADOS = ['CERRADO', 'ENVIADO'];

export default function useTopeTienda(corridaId, sucursalId, estadoPedido, enabled) {
  const [propuesta, setPropuesta] = useState(null);
  const [cerrado, setCerrado] = useState(null);
  const [nonce, setNonce] = useState(0);
  const requestId = useRef(0);
  const recargar = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    const id = ++requestId.current;
    const vigente = () => id === requestId.current;
    const limpiar = () => { setPropuesta(null); setCerrado(null); };
    if (!enabled || !(estadoPedido === 'BORRADOR' || CERRADOS.includes(estadoPedido))) {
      limpiar();
      return;
    }
    if (estadoPedido === 'BORRADOR') {
      getRecorte(corridaId, sucursalId)
        .then((body) => { if (vigente()) { setPropuesta(body); setCerrado(null); } })
        .catch(() => { if (vigente()) limpiar(); });
      return;
    }
    getTopesCorrida(corridaId)
      .then((body) => {
        if (!vigente()) return;
        setPropuesta(null);
        setCerrado((body.tiendas || []).find((t) => t.sucursal_id === sucursalId) || null);
      })
      .catch(() => { if (vigente()) limpiar(); });
  }, [enabled, corridaId, sucursalId, estadoPedido, nonce]);

  return { propuesta, cerrado, recargar, fijarPropuesta: setPropuesta };
}
