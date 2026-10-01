'use client';
/**
 * The budget cap of the tienda page: the cap data (`useTopeTienda`), the
 * recorte flow (`useRecorte`) and the callbacks that keep them in step with the
 * rest of the page. `alCambiar` runs after any change of the pedido (an edit,
 * a lifecycle action, a recorte) and reads the cap again, so the banner always
 * follows the quantities; `refresco` counts the recortes the lines must reload for.
 */
import { useCallback, useState } from 'react';
import useRecorte from './useRecorte';
import useTopeTienda from './useTopeTienda';

export default function useTopePedido({ corridaId, sucursalId, estadoPedido, habilitado, recargarBase }) {
  const tope = useTopeTienda(corridaId, sucursalId, estadoPedido, habilitado);
  const { recargar } = tope;
  const alCambiar = useCallback(() => { recargarBase(); recargar(); }, [recargarBase, recargar]);
  const [refresco, setRefresco] = useState(0);
  const alAplicar = useCallback(() => { alCambiar(); setRefresco((n) => n + 1); }, [alCambiar]);
  const recorte = useRecorte({
    corridaId, sucursalId, propuesta: tope.propuesta, fijarPropuesta: tope.fijarPropuesta, alCambiar: alAplicar,
  });
  return { propuesta: tope.propuesta, cerrado: tope.cerrado, alCambiar, refresco, recorte };
}
