'use client';
/** Topes por tienda: the budget cap switch and one cap per tienda (ADMIN edits, COMPRAS reads). */
import MotoredLayout from '../../motored-layout';
import TopesContainer from '../../../../components/motored/pedidos/TopesContainer';

export default function TopesPage() {
  return (
    <MotoredLayout>
      <TopesContainer />
    </MotoredLayout>
  );
}
