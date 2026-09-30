'use client';
/** ADMIN-only login log ("quién entra y cuándo"). */
import MotoredLayout from '../motored-layout';
import IngresosContainer from '../../../components/motored/ingresos/IngresosContainer';

export default function IngresosPage() {
  return (
    <MotoredLayout>
      <IngresosContainer />
    </MotoredLayout>
  );
}
