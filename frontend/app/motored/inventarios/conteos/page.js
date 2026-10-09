'use client';
/** "Conteos de inventario" (ADMIN, LIDER_INVENTARIOS and GERENCIA): the landing page of LIDER_INVENTARIOS. */
import MotoredLayout from '../../motored-layout';
import ConteosContainer from '../../../../components/motored/inventarios/ConteosContainer';

export default function ConteosPage() {
  return (
    <MotoredLayout>
      <ConteosContainer />
    </MotoredLayout>
  );
}
