'use client';
/**
 * frontend/app/motored/cargas/[id]/page.js
 *
 * Ruta de detalle de una carga (sdd/motored-pedidos-ingesta, Phase 10,
 * task 10.2) -- delega toda la lógica a `CargaDetalle.js`, mismo criterio
 * que `app/motored/maestros/page.js` delega a `MaestrosTabs.js`.
 */
import { useParams } from 'next/navigation';
import MotoredLayout from '../../motored-layout';
import CargaDetalle from '../../../../components/motored/cargas/CargaDetalle';

export default function CargaDetallePage() {
  const { id } = useParams();
  return (
    <MotoredLayout>
      <CargaDetalle cargaId={id} />
    </MotoredLayout>
  );
}
