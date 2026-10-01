'use client';
/** Corrida detail (ADMIN and COMPRAS): the tiendas of one corrida and their pedido. */
import { useParams } from 'next/navigation';
import MotoredLayout from '../../motored-layout';
import CorridaDetalleContainer from '../../../../components/motored/pedidos/CorridaDetalleContainer';

export default function CorridaDetallePage() {
  const { id } = useParams();
  return (
    <MotoredLayout>
      <CorridaDetalleContainer corridaId={id} />
    </MotoredLayout>
  );
}
