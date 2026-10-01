'use client';
/** Confirmation to recalculate the FALLIDA tiendas in a new corrida (same fecha de corte, only those tiendas). */
import DialogoPedido from './DialogoPedido';
import { plural } from './formato';
import { mutedStyle } from './styles';

export default function RecalcularDialog({ tiendas, ocupado, error, onConfirm, onCancel }) {
  const n = tiendas.length;
  return (
    <DialogoPedido
      titulo="Recalcular las tiendas fallidas" textoConfirmar="Recalcular"
      descripcion={(
        <>
          <span>{`Se calculará una corrida nueva con ${n} ${plural(n, 'tienda', 'tiendas')}: ${tiendas.map((t) => t.nombre).join(', ')}.`}</span>
          <span style={mutedStyle}>La corrida actual y sus pedidos no cambian.</span>
        </>
      )}
      ocupado={ocupado} error={error} onConfirm={onConfirm} onCancel={onCancel}
    />
  );
}
