'use client';
/**
 * frontend/app/motored/maestros/page.js
 *
 * Masters screen (sdd/motored-pedidos-cimientos). ONE page, 4 tabs per the
 * proposal (§7.12: "Maestros screen, 4 tabs: Sucursales · Bodegas ·
 * Referencias · Proveedores") -- not separate sidebar entries.
 *
 * Per direct user feedback, "Salud de maestros" is no longer a standalone
 * 5th tab -- each tab below carries `entidadSalud` (the backend's own
 * hallazgo.entidad value for that master) so `MaestrosTabs.js` can render
 * a small traffic-light dot next to its label instead. `proveedor` has no
 * health check in `services/salud.py` today, so it deliberately gets no
 * `entidadSalud` -- no dot, not a green one, since there is genuinely
 * nothing being checked for it yet.
 */
import MotoredLayout from '../motored-layout';
import MaestrosTabs from '../../../components/motored/maestros/MaestrosTabs';
import SucursalesTab from '../../../components/motored/maestros/SucursalesTab';
import BodegasTab from '../../../components/motored/maestros/BodegasTab';
import ProveedoresTab from '../../../components/motored/maestros/ProveedoresTab';
import ReferenciasTab from '../../../components/motored/maestros/ReferenciasTab';

const TABS = [
  { id: 'sucursales', label: 'Sucursales', entidadSalud: 'sucursal', render: () => <SucursalesTab /> },
  { id: 'bodegas', label: 'Bodegas', entidadSalud: 'bodega', render: () => <BodegasTab /> },
  { id: 'proveedores', label: 'Proveedores', render: () => <ProveedoresTab /> },
  { id: 'referencias', label: 'Referencias', entidadSalud: 'referencia', render: () => <ReferenciasTab /> },
];

export default function MaestrosPage() {
  return (
    <MotoredLayout>
      <MaestrosTabs tabs={TABS} />
    </MotoredLayout>
  );
}
