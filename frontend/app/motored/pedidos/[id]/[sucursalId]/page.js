'use client';
/** Pedido of one tienda (ADMIN and COMPRAS): header, totals, class summary and lines. */
import { useParams } from 'next/navigation';
import MotoredLayout from '../../../motored-layout';
import PedidoTiendaContainer from '../../../../../components/motored/pedidos/PedidoTiendaContainer';

export default function PedidoTiendaPage() {
  const { id, sucursalId } = useParams();
  return (
    <MotoredLayout>
      <PedidoTiendaContainer corridaId={id} sucursalId={sucursalId} />
    </MotoredLayout>
  );
}
