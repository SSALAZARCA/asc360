'use client';
/** ADMIN annuls a conteo; the reason is required. Readings are kept and the pairs' link stops working. */
import { useState } from 'react';
import DialogoPedido from '../pedidos/DialogoPedido';
import { anularConteo } from '../../../lib/motored/conteosApi';
import { labelStyle } from './estilos';

export default function AnularConteoDialog({ conteo, onCancel, onListo }) {
  const [motivo, setMotivo] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState('');

  const confirmar = async () => {
    setOcupado(true);
    setError('');
    try {
      await anularConteo(conteo.id, motivo.trim());
      onListo();
    } catch (err) {
      setError(err.message || 'No se pudo anular el conteo.');
      setOcupado(false);
    }
  };

  return (
    <DialogoPedido
      titulo={`Anular conteo · ${conteo.sucursal.nombre}`}
      descripcion={<span>El conteo no se podrá retomar. Las lecturas quedan guardadas y el enlace de las parejas deja de funcionar.</span>}
      error={error} ocupado={ocupado} confirmarDeshabilitado={motivo.trim() === ''}
      textoConfirmar="Anular conteo" onConfirm={confirmar} onCancel={onCancel}
    >
      <label style={labelStyle}>
        Motivo
        <textarea rows={3} maxLength={2000} value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Explique por qué se anula" />
      </label>
    </DialogoPedido>
  );
}
