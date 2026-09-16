'use client';
/**
 * frontend/app/motored/maestros/page.js
 *
 * Masters screen (sdd/motored-pedidos-cimientos). ONE page, 4 tabs per the
 * proposal (§7.12: "Maestros screen, 4 tabs: Sucursales · Bodegas ·
 * Referencias · Proveedores") -- not 4 separate sidebar entries.
 */
import MotoredLayout from '../motored-layout';
import MaestrosTabs from '../../../components/motored/maestros/MaestrosTabs';
import SucursalesTab from '../../../components/motored/maestros/SucursalesTab';
import BodegasTab from '../../../components/motored/maestros/BodegasTab';
import ProveedoresTab from '../../../components/motored/maestros/ProveedoresTab';
import ReferenciasTab from '../../../components/motored/maestros/ReferenciasTab';

const TABS = [
  { id: 'sucursales', label: 'Sucursales', render: () => <SucursalesTab /> },
  { id: 'bodegas', label: 'Bodegas', render: () => <BodegasTab /> },
  { id: 'proveedores', label: 'Proveedores', render: () => <ProveedoresTab /> },
  { id: 'referencias', label: 'Referencias', render: () => <ReferenciasTab /> },
];

export default function MaestrosPage() {
  return (
    <MotoredLayout>
      <MaestrosTabs tabs={TABS} />
    </MotoredLayout>
  );
}
