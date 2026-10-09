'use client';
/** One inventory count: start, pair access, live panel or result (odd/motored-conteos-inventario, WU11/WU12). */
import { useParams } from 'next/navigation';
import MotoredLayout from '../../../motored-layout';
import ConteoDetalleContainer from '../../../../../components/motored/inventarios/ConteoDetalleContainer';

export default function ConteoDetallePage() {
  const { id } = useParams();
  return (
    <MotoredLayout>
      <ConteoDetalleContainer conteoId={id} />
    </MotoredLayout>
  );
}
