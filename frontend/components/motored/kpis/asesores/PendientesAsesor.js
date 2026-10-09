'use client';
import PendientesIngreso from './PendientesIngreso';
import PendientesTraslados from './PendientesTraslados';

/**
 * The two "pendientes" cards of the asesor view side by side (invoices and transfers, same height). The columns
 * stack when the container is narrower than about 900px (phone and the public link).
 */
export default function PendientesAsesor({ data, enlace }) {
  return (
    <div data-testid="pendientes-asesor" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 420px), 1fr))', gap: 16 }}>
      <PendientesIngreso data={data} enlace={enlace} />
      <PendientesTraslados data={data} enlace={enlace} />
    </div>
  );
}
