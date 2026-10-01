'use client';
/** How many lines of a tienda pedido are not a multiple of the pack (a warning, never a block). */
import { useEffect, useState } from 'react';
import { listarLineas } from '../../../lib/motored/pedidosApi';

/** The count, or `null` while it loads or when it cannot be read (the dialog then says nothing). */
export default function useFueraDeEmpaque(corridaId, sucursalId) {
  const [total, setTotal] = useState(null);

  useEffect(() => {
    let vigente = true;
    listarLineas(corridaId, { sucursal_id: sucursalId, solo_fuera_empaque: true, limite: 1 })
      .then((pagina) => { if (vigente) setTotal(Number(pagina.total)); })
      .catch(() => { if (vigente) setTotal(null); });
    return () => { vigente = false; };
  }, [corridaId, sucursalId]);

  return total;
}
