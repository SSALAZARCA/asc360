'use client';
/** Confirmation of "Aplicar recorte": the lines to cut, the value freed and the new total. Nothing is cut before it. */
import { formatCOP } from '../../../lib/motored/formatCOP';
import DialogoPedido from './DialogoPedido';
import { plural } from './formato';
import { mutedStyle } from './styles';
import { resumenRecorte } from './tope';

export default function ConfirmarRecorteDialog({ nombre, propuesta, actualizada, ocupado, error, onConfirm, onCancel }) {
  const { lineas, liberado } = resumenRecorte(propuesta);
  const resumen = `${plural(lineas, 'Se recortará', 'Se recortarán')} ${lineas} ${plural(lineas, 'línea', 'líneas')} y se ${plural(lineas, 'liberará', 'liberarán')} ${formatCOP(liberado)}: el pedido pasa de ${formatCOP(propuesta.valor_actual)} a ${formatCOP(propuesta.valor_final)} (tope ${formatCOP(propuesta.tope)}).`;
  return (
    <DialogoPedido
      titulo={`Aplicar recorte al pedido de ${nombre}`} textoConfirmar="Aplicar recorte"
      descripcion={(
        <>
          {actualizada && <span style={{ fontWeight: 600 }}>Los valores de abajo son los de la propuesta actualizada.</span>}
          <span>{resumen}</span>
          <span style={mutedStyle}>Después puede seguir ajustando a mano cualquier cantidad.</span>
        </>
      )}
      ocupado={ocupado} error={error} onConfirm={onConfirm} onCancel={onCancel}
    />
  );
}
