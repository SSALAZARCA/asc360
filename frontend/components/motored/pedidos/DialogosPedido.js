'use client';
/** Renders the dialog that `useAccionesPedido` has open (if any) for the pedidos of one corrida. */
import CerrarTiendaDialog from './CerrarTiendaDialog';
import CerrarTodasDialog from './CerrarTodasDialog';
import CorregirEnvioModal from './CorregirEnvioModal';
import MarcarEnviadoModal from './MarcarEnviadoModal';
import RecalcularDialog from './RecalcularDialog';
import ReabrirDialog from './ReabrirDialog';

export default function DialogosPedido({ acciones, corridaId, fechaCorte, yaCerradas = 0 }) {
  const { dialogo, ocupado, error, cancelar, confirmar } = acciones;
  if (!dialogo) return null;
  const comun = { ocupado, error, onConfirm: confirmar, onCancel: cancelar };
  const [primera] = dialogo.tiendas;
  switch (dialogo.tipo) {
    case 'cerrar':
      if (dialogo.tiendas.length === 1 && !dialogo.todas) {
        return <CerrarTiendaDialog corridaId={corridaId} tienda={primera} {...comun} />;
      }
      return <CerrarTodasDialog tiendas={dialogo.tiendas} todas={Boolean(dialogo.todas)} yaCerradas={yaCerradas} {...comun} />;
    case 'reabrir':
      return <ReabrirDialog tienda={primera} {...comun} />;
    case 'enviar':
      return <MarcarEnviadoModal tiendas={dialogo.tiendas} fechaCorte={fechaCorte} {...comun} />;
    case 'corregir':
      return <CorregirEnvioModal tienda={primera} {...comun} />;
    default:
      return <RecalcularDialog tiendas={dialogo.tiendas} {...comun} />;
  }
}
