'use client';
/** Reopen ONE closed tienda pedido: the motivo is required (1..500) and the HMCL file already downloaded becomes invalid. */
import { useState } from 'react';
import DialogoPedido from './DialogoPedido';
import { labelStyle, mutedStyle } from './styles';

export default function ReabrirDialog({ tienda, ocupado, error, onConfirm, onCancel }) {
  const [motivo, setMotivo] = useState('');
  return (
    <DialogoPedido
      titulo={`Reabrir el pedido de ${tienda.nombre}`} textoConfirmar="Reabrir pedido"
      confirmarDeshabilitado={motivo.trim() === ''}
      descripcion={(
        <>
          <span>El pedido vuelve a Borrador para poder ajustarlo. Las demás tiendas no cambian.</span>
          <span style={{ ...mutedStyle, fontWeight: 600 }}>
            El archivo HMCL que descargó antes queda inválido; vuelva a exportar después de cerrar.
          </span>
        </>
      )}
      ocupado={ocupado} error={error} onConfirm={() => onConfirm(motivo.trim())} onCancel={onCancel}
    >
      <label style={labelStyle}>
        Motivo
        <textarea
          rows={3} maxLength={500} value={motivo} onChange={(e) => setMotivo(e.target.value)}
          placeholder="Explique por qué se reabre"
        />
      </label>
    </DialogoPedido>
  );
}
