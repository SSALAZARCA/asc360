'use client';
/**
 * Everything the Resumen tab needs before Aplicar on a raw ERP VENTAS carga
 * in VALIDADO: the refs without a line, the planned month purge, the
 * "Entiendo" acknowledgement and whether (and why) Aplicar is blocked.
 * Both endpoints are ADMIN/COMPRAS only: `puedeRevisar` is false for any
 * other role and while the role is not known yet. Other cargas and other
 * roles request nothing and never block.
 */
import { useEffect, useState } from 'react';
import { getVaciadoPrevisto } from '../../../lib/motored/api';
import useReferenciasSinLinea from './useReferenciasSinLinea';
import { muestraSimulacionVentas, TEXTO_GUARDAR_ANTES, textoBloqueoAplicar } from './ventasErp';

const MENSAJE_ENTIENDO = 'Marque «Entiendo» en el aviso de borrado para poder aplicar.';

function useVaciadoPrevisto(cargaId, activo) {
  const [estado, setEstado] = useState({ filas: null, error: '' });
  useEffect(() => {
    if (!activo) return;
    getVaciadoPrevisto(cargaId)
      .then((filas) => setEstado({ filas: filas || [], error: '' }))
      .catch((err) => setEstado({ filas: null, error: err.message || 'error' }));
  }, [cargaId, activo]);
  const requiereConfirmar = Boolean(estado.error) || Boolean(estado.filas?.length);
  return { ...estado, requiereConfirmar, cargando: !estado.error && estado.filas === null };
}

/**
 * `{ bloqueado, mensaje }` of Aplicar: unsaved line choices first, then refs
 * without a line on the server, then the purge acknowledgement.
 */
function bloqueoAplicar({ sinLinea, vaciado, entendido }) {
  if (sinLinea.cantidadPendientes > 0) return { bloqueado: true, mensaje: TEXTO_GUARDAR_ANTES };
  if (!sinLinea.error) {
    if (!sinLinea.datos) return { bloqueado: true, mensaje: '' };
    const n = sinLinea.datos.sin_linea.length;
    if (n > 0) return { bloqueado: true, mensaje: textoBloqueoAplicar(n) };
  }
  if (vaciado.cargando) return { bloqueado: true, mensaje: '' };
  if (vaciado.requiereConfirmar && !entendido) return { bloqueado: true, mensaje: MENSAJE_ENTIENDO };
  return { bloqueado: false, mensaje: '' };
}

export default function useSimulacionVentas(carga, puedeRevisar) {
  const activa = Boolean(puedeRevisar) && muestraSimulacionVentas(carga);
  const sinLinea = useReferenciasSinLinea(carga.id, activa);
  const vaciado = useVaciadoPrevisto(carga.id, activa);
  const [entendido, setEntendido] = useState(false);
  const bloqueo = activa ? bloqueoAplicar({ sinLinea, vaciado, entendido }) : { bloqueado: false, mensaje: '' };
  return { activa, sinLinea, vaciado, entendido, setEntendido, bloqueo };
}
