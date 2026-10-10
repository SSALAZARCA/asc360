'use client';
/**
 * The Iniciar flow (WU11, WU15). Iniciar may answer two 409 warnings, each
 * with its own confirmation flag: INVENTARIO_ANTIGUO (`confirmarAntiguedad`)
 * and PENDIENTES_POR_SANEAR (`confirmarPendientes`). Either may come first;
 * a confirmed one is kept for the next retry, so the leader may confirm both.
 * Cancelling a dialog forgets the confirmations.
 */
import { useRef, useState } from 'react';
import { iniciarConteo } from '../../../lib/motored/conteosApi';

const SIN_CONFIRMAR = { confirmarAntiguedad: false, confirmarPendientes: false };

function plural(n, singular, varios) {
  return `${n} ${n === 1 ? singular : varios}`;
}

/** The dialog for a warning not yet confirmed; null for any other error. */
function avisoDe(err, opciones) {
  if (err.code === 'INVENTARIO_ANTIGUO' && !opciones.confirmarAntiguedad) {
    return { flag: 'confirmarAntiguedad', titulo: 'El inventario no está al día', mensaje: err.message };
  }
  if (err.code === 'PENDIENTES_POR_SANEAR' && !opciones.confirmarPendientes) {
    const datos = err.datos || {};
    const facturas = plural(Number(datos.facturas) || 0, 'factura', 'facturas');
    const traslados = plural(Number(datos.traslados) || 0, 'traslado', 'traslados');
    return {
      flag: 'confirmarPendientes',
      titulo: 'Hay pendientes por sanear',
      mensaje: `Esta tienda tiene ${facturas} y ${traslados} pendientes. ¿Iniciar igual?`,
    };
  }
  return null;
}

export default function useIniciarConteo(conteoId, onIniciado) {
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState('');
  const [aviso, setAviso] = useState(null);
  const confirmados = useRef(SIN_CONFIRMAR);

  const iniciar = async (opciones) => {
    setOcupado(true);
    setError('');
    try {
      const salida = await iniciarConteo(conteoId, opciones);
      setAviso(null);
      onIniciado(salida);
    } catch (err) {
      const siguiente = avisoDe(err, opciones);
      setAviso(siguiente);
      if (!siguiente) setError(err.message || 'No se pudo iniciar el conteo.');
      setOcupado(false);
    }
  };

  const empezar = () => {
    confirmados.current = SIN_CONFIRMAR;
    iniciar(SIN_CONFIRMAR);
  };
  const confirmar = () => {
    confirmados.current = { ...confirmados.current, [aviso.flag]: true };
    iniciar(confirmados.current);
  };
  const cancelar = () => {
    confirmados.current = SIN_CONFIRMAR;
    setAviso(null);
  };
  return { ocupado, error, aviso, empezar, confirmar, cancelar };
}
