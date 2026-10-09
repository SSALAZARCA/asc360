'use client';
/** "Ingresos facturas" (ADMIN, COMPRAS, GERENCIA and COORDINADOR_REPUESTOS): pending invoice intakes. */
import MotoredLayout from '../../motored-layout';
import IngresosFacturasContainer from '../../../../components/motored/gestion-repuestos/IngresosFacturasContainer';

export default function IngresosFacturasPage() {
  return (
    <MotoredLayout>
      <IngresosFacturasContainer />
    </MotoredLayout>
  );
}
