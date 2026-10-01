'use client';
/**
 * The real corridas a scenario can be compared with: calculated, not a
 * scenario, same fecha de corte and proveedor, most recent first (the order
 * the list endpoint answers in). The first one is the default.
 */
import { useEffect, useState } from 'react';
import { listarCorridas } from '../../../lib/motored/pedidosApi';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';

// BORRADOR is "calculated"; CERRADA is how a corrida closed before the per-tienda lifecycle reads.
const CALCULADAS = ['BORRADOR', 'CERRADA'];
const MAXIMO = 50;

export const esComparable = (corrida) => !corrida.es_escenario && CALCULADAS.includes(corrida.estado);

export default function useRealesComparables(escenario) {
  const [estado, setEstado] = useState({ items: null, error: '' });
  const { fecha_corte: corte, proveedor_id: proveedor } = escenario;

  useEffect(() => {
    let vivo = true;
    const dia = String(corte).slice(0, 10);
    listarCorridas({ escenario: false, desde: dia, hasta: dia, proveedor_id: proveedor, limite: MAXIMO })
      .then((pagina) => { if (vivo) setEstado({ items: pagina.items.filter(esComparable), error: '' }); })
      .catch((fallo) => {
        if (vivo) setEstado({ items: null, error: mensajeConCodigo(fallo, 'No se pudo buscar las corridas reales para comparar.') });
      });
    return () => { vivo = false; };
  }, [corte, proveedor]);

  return estado;
}
