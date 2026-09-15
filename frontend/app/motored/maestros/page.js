'use client';
/**
 * frontend/app/motored/maestros/page.js
 *
 * Masters screen (sdd/motored-pedidos-cimientos, Phase 6, task 6.2).
 * Wrapped in `MotoredLayout` (own route guard) -- demonstrates
 * list/create/update/deactivate end-to-end for `sucursal`, plus the
 * bulk-upload validar/carga flow, per this slice's scope.
 */
import MotoredLayout from '../motored-layout';
import SucursalesTab from '../../../components/motored/maestros/SucursalesTab';

export default function MaestrosPage() {
  return (
    <MotoredLayout>
      <SucursalesTab />
    </MotoredLayout>
  );
}
