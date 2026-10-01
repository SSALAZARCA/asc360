'use client';
/** Confirmation to close ONE tienda pedido; it shows the lines outside the pack (a warning, not a block). */
import { formatCOP } from '../../../lib/motored/formatCOP';
import DialogoPedido from './DialogoPedido';
import useFueraDeEmpaque from './useFueraDeEmpaque';
import { plural, unidades } from './formato';
import { mutedStyle } from './styles';

function AvisoEmpaque({ total }) {
  if (total == null) return null;
  if (total === 0) return <span style={mutedStyle}>Ninguna línea está fuera del empaque.</span>;
  return (
    <span style={{ ...mutedStyle, fontWeight: 600 }}>
      {`${total} ${plural(total, 'línea no es múltiplo', 'líneas no son múltiplo')} del empaque. Se puede cerrar igual.`}
    </span>
  );
}

export default function CerrarTiendaDialog({ corridaId, tienda, ocupado, error, onConfirm, onCancel }) {
  const fuera = useFueraDeEmpaque(corridaId, tienda.sucursal_id);
  const resumen = `Se cerrará el pedido de ${tienda.nombre}: ${unidades(tienda.unidades_a_pedir)} unidades por ${formatCOP(tienda.valor_a_pedir)}.`;
  return (
    <DialogoPedido
      titulo={`Cerrar el pedido de ${tienda.nombre}`} textoConfirmar="Cerrar pedido"
      descripcion={(
        <>
          <span>{resumen}</span>
          <span style={mutedStyle}>Cerrado, el pedido ya no se puede ajustar (se puede reabrir mientras no esté enviado).</span>
          <AvisoEmpaque total={fuera} />
        </>
      )}
      ocupado={ocupado} error={error} onConfirm={onConfirm} onCancel={onCancel}
    />
  );
}
