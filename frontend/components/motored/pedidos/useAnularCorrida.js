'use client';
/** State of the "Anular corrida" dialog: target, motivo, request, coded error. */
import { useCallback, useState } from 'react';
import { anularCorrida } from '../../../lib/motored/pedidosApi';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';

export default function useAnularCorrida(onDone) {
  const [corrida, setCorrida] = useState(null);
  const [motivo, setMotivo] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const abrir = useCallback((objetivo) => {
    setCorrida(objetivo);
    setMotivo('');
    setError('');
  }, []);
  const cerrar = useCallback(() => setCorrida(null), []);

  const confirmar = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      await anularCorrida(corrida.id, motivo.trim());
      setCorrida(null);
      onDone?.();
    } catch (fallo) {
      setError(mensajeConCodigo(fallo, 'No se pudo anular la corrida.'));
    } finally {
      setBusy(false);
    }
  }, [corrida, motivo, onDone]);

  return { corrida, motivo, setMotivo, busy, error, abrir, cerrar, confirmar };
}
