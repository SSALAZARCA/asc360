'use client';
/**
 * "Aplicar recorte" of one draft tienda: the confirmation dialog, the request
 * with the token of the proposal the user saw, and what happens when the
 * server refuses. A stale proposal (E-CORRIDA-060) keeps the dialog open with
 * the fresh figures (or closes it when nothing is left to cut); any other
 * coded rejection closes it and leaves the message on the screen. After any
 * answer `alCambiar` reads the pedido again (header, lines, proposal).
 */
import { useCallback, useState } from 'react';
import { aplicarRecorte } from '../../../lib/motored/pedidosApi';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';
import { formatCOP } from '../../../lib/motored/formatCOP';
import { plural } from './formato';
import { PROPUESTA_DESACTUALIZADA, propuestaFresca, tieneRecortes } from './tope';

const SIN_APLICAR = 'No se pudo aplicar el recorte.';

function avisoDeAplicado({ lineas_recortadas: n, valor_liberado: liberado }) {
  const lineas = `${n} ${plural(n, 'línea recortada', 'líneas recortadas')}`;
  return { tipo: 'ok', texto: `Recorte aplicado: ${lineas}, ${formatCOP(liberado)} liberados.` };
}

export default function useRecorte({ corridaId, sucursalId, propuesta, fijarPropuesta, alCambiar }) {
  const [abierto, setAbierto] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState('');
  const [actualizada, setActualizada] = useState(false);
  const [aviso, setAviso] = useState(null);

  const abrir = useCallback(() => { setError(''); setActualizada(false); setAbierto(true); }, []);
  const cancelar = useCallback(() => setAbierto(false), []);
  const descartarAviso = useCallback(() => setAviso(null), []);

  const rechazar = useCallback((fallo) => {
    const texto = mensajeConCodigo(fallo, SIN_APLICAR);
    const fresca = propuestaFresca(fallo);
    if (fresca) fijarPropuesta(fresca);
    if (!fallo.status) { setError(texto); return; } // no answer from the server: stay and retry
    const seguir = fresca ? tieneRecortes(fresca) : fallo.code === PROPUESTA_DESACTUALIZADA;
    if (seguir) {
      setError(texto);
      setActualizada(true);
    } else {
      setAbierto(false);
      setAviso({ tipo: 'error', texto });
    }
    alCambiar();
  }, [fijarPropuesta, alCambiar]);

  const confirmar = useCallback(async () => {
    setOcupado(true);
    setError('');
    try {
      const resultado = await aplicarRecorte(corridaId, sucursalId, propuesta.token);
      setAbierto(false);
      setAviso(avisoDeAplicado(resultado));
      alCambiar();
    } catch (fallo) {
      rechazar(fallo);
    } finally {
      setOcupado(false);
    }
  }, [corridaId, sucursalId, propuesta, alCambiar, rechazar]);

  return { abierto, ocupado, error, actualizada, aviso, abrir, cancelar, confirmar, descartarAviso };
}
