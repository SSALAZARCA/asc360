'use client';
/**
 * Inline edit of "Cantidad a pedir". The new quantity shows at once; if the
 * server refuses, the line goes back to what it was and the Spanish message
 * (with its code) stays under the cell. A rule that depends on the state of
 * the pedido (a 409) also reads the lines and the header again, so the screen
 * shows what is true now: 066 brings the fresh quantity, 052 turns the table
 * read-only. A line being saved is locked by its cell, so each line is saved
 * one at a time while different lines stay independent.
 */
import { useCallback, useState } from 'react';
import { editarLinea } from '../../../lib/motored/pedidosApi';
import { NETWORK_MESSAGE, mensajeConCodigo } from '../../../lib/motored/httpErrors';
import { lineaConCantidad } from './cantidad';

const SIN_GUARDAR = 'No se pudo guardar la cantidad.';

function textoDelError(err) {
  if (!err || !err.status) return `${SIN_GUARDAR} ${NETWORK_MESSAGE}`;
  return mensajeConCodigo(err, SIN_GUARDAR);
}

const sinClave = (objeto, id) => {
  if (!(id in objeto)) return objeto;
  const { [id]: _quitada, ...resto } = objeto;
  return resto;
};

export default function useEdicionLinea({ corridaId, parchear, recargar, alCambiarPedido }) {
  const [guardando, setGuardando] = useState({});
  const [errores, setErrores] = useState({});

  const olvidarError = useCallback((id) => setErrores((e) => sinClave(e, id)), []);

  const guardar = useCallback(async (linea, cantidad) => {
    const { id } = linea;
    if (Number(linea.pedido_final) === cantidad) return;
    setGuardando((g) => ({ ...g, [id]: true }));
    olvidarError(id);
    parchear(id, () => lineaConCantidad(linea, cantidad));
    try {
      const { linea: guardada } = await editarLinea(corridaId, id, { pedido_final: cantidad, esperado: linea.pedido_final });
      parchear(id, () => guardada);
      alCambiarPedido();
    } catch (err) {
      parchear(id, () => linea);
      setErrores((e) => ({ ...e, [id]: textoDelError(err) }));
      if (err && err.status === 409) {
        recargar();
        alCambiarPedido();
      }
    } finally {
      setGuardando((g) => sinClave(g, id));
    }
  }, [corridaId, parchear, recargar, alCambiarPedido, olvidarError]);

  return { guardar, olvidarError, guardando, errores };
}
