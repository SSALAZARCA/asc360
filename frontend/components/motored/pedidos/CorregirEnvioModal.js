'use client';
/** Correct the HMCL order number of a tienda that was already sent (F4-15); the send date does not change. */
import { useState } from 'react';
import InfoTooltip from '../InfoTooltip';
import DialogoPedido from './DialogoPedido';
import { labelStyle, mutedStyle } from './styles';

const ORDEN_TEXTO = 'Orden de pedido: el número que HMCL le dio a este pedido al recibirlo.';
const MAX_NUMERO_ORDEN = 50;

export default function CorregirEnvioModal({ tienda, ocupado, error, onConfirm, onCancel }) {
  const actual = tienda.envio ? String(tienda.envio.numero_orden) : '';
  const [numero, setNumero] = useState(actual);
  const limpio = numero.trim();
  return (
    <DialogoPedido
      titulo={`Corregir número de orden de ${tienda.nombre}`} textoConfirmar="Corregir número"
      confirmarDeshabilitado={limpio === '' || limpio === actual}
      descripcion={(
        <>
          <span>{`El número de orden actual es ${actual || '—'}. El cambio queda registrado con quién lo hizo y cuándo.`}</span>
          <span style={mutedStyle}>La fecha de envío no cambia.</span>
        </>
      )}
      ocupado={ocupado} error={error} onConfirm={() => onConfirm(limpio)} onCancel={onCancel}
    >
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: '4px' }}>
        <label style={{ ...labelStyle, flex: 1 }}>
          Número de orden
          <input
            aria-label={`Número de orden de ${tienda.nombre}`} maxLength={MAX_NUMERO_ORDEN} value={numero}
            onChange={(e) => setNumero(e.target.value)}
          />
        </label>
        <InfoTooltip text={ORDEN_TEXTO} />
      </div>
    </DialogoPedido>
  );
}
