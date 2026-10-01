'use client';
/** Confirmation to close several tienda pedidos at once (every draft, or the selected ones): all or nothing. */
import DialogoPedido from './DialogoPedido';
import { plural } from './formato';
import { mutedStyle } from './styles';

export default function CerrarTodasDialog({ tiendas, todas, yaCerradas, ocupado, error, onConfirm, onCancel }) {
  const n = tiendas.length;
  const que = todas ? 'en Borrador' : 'seleccionados';
  return (
    <DialogoPedido
      titulo={todas ? 'Cerrar los pedidos en Borrador' : 'Cerrar los pedidos seleccionados'} textoConfirmar="Cerrar pedidos"
      descripcion={(
        <>
          <span>{`${plural(n, 'Se cerrará', 'Se cerrarán')} ${n} ${plural(n, 'pedido', 'pedidos')} ${que}.`}</span>
          {todas && yaCerradas > 0 && (
            <span style={mutedStyle}>
              {`${yaCerradas} ${plural(yaCerradas, 'pedido ya estaba cerrado o enviado', 'pedidos ya estaban cerrados o enviados')}.`}
            </span>
          )}
          <span style={mutedStyle}>Si alguno no se puede cerrar, no se cierra ninguno (todo o nada).</span>
        </>
      )}
      ocupado={ocupado} error={error} onConfirm={onConfirm} onCancel={onCancel}
    />
  );
}
