'use client';
/**
 * frontend/app/motored/maestros/page.js
 *
 * Masters + movement uploads screen. Started (sdd/motored-pedidos-
 * cimientos) as ONE page, 4 tabs per the proposal (§7.12: "Maestros screen,
 * 4 tabs: Sucursales · Bodegas · Referencias · Proveedores") -- not
 * separate sidebar entries.
 *
 * Grew to 10 tabs (sdd/motored-cargas-tipo-declarado; proposal decision #2
 * "ONE screen", design D3/D4): the standalone "Cargas" screen/sidebar entry
 * was retired, and its 6 movement types now live here as `MovimientoTab`
 * entries, grouped under 'Movimientos' vs. the original 4 under
 * 'Maestros' (`MaestrosTabs.js` renders the group label). Bodegas/
 * Referencias are UNCHANGED (proposal decision #3) -- still their own Fase
 * 1 `BulkUploadModal` tabs, byte-for-byte as before.
 *
 * Per direct user feedback, "Salud de maestros" is no longer a standalone
 * 5th tab -- each tab below carries `entidadSalud` (the backend's own
 * hallazgo.entidad value for that master) so `MaestrosTabs.js` can render
 * a small traffic-light dot next to its label instead. `proveedor` has no
 * health check in `services/salud.py` today, so it deliberately gets no
 * `entidadSalud` -- no dot, not a green one, since there is genuinely
 * nothing being checked for it yet. The 6 movement tabs never had a health
 * check either, same reasoning.
 */
import MotoredLayout from '../motored-layout';
import MaestrosTabs from '../../../components/motored/maestros/MaestrosTabs';
import SucursalesTab from '../../../components/motored/maestros/SucursalesTab';
import BodegasTab from '../../../components/motored/maestros/BodegasTab';
import ProveedoresTab from '../../../components/motored/maestros/ProveedoresTab';
import ReferenciasTab from '../../../components/motored/maestros/ReferenciasTab';
import MovimientoTab from '../../../components/motored/cargas/MovimientoTab';

const TABS = [
  { id: 'sucursales', label: 'Sucursales', group: 'Maestros', entidadSalud: 'sucursal', render: () => <SucursalesTab /> },
  { id: 'bodegas', label: 'Bodegas', group: 'Maestros', entidadSalud: 'bodega', render: () => <BodegasTab /> },
  { id: 'proveedores', label: 'Proveedores', group: 'Maestros', render: () => <ProveedoresTab /> },
  { id: 'referencias', label: 'Referencias', group: 'Maestros', entidadSalud: 'referencia', render: () => <ReferenciasTab /> },
  { id: 'ventas', label: 'Ventas', group: 'Movimientos', render: () => <MovimientoTab tipo="VENTAS" label="Ventas" /> },
  { id: 'inventario', label: 'Inventario', group: 'Movimientos', render: () => <MovimientoTab tipo="INVENTARIO" label="Inventario" /> },
  { id: 'backorder', label: 'Backorder', group: 'Movimientos', render: () => <MovimientoTab tipo="BACKORDER" label="Backorder" /> },
  { id: 'demanda_perdida', label: 'Demanda perdida', group: 'Movimientos', render: () => <MovimientoTab tipo="DEMANDA_PERDIDA" label="Demanda perdida" /> },
  { id: 'facturas_pedidos', label: 'Facturas de pedidos', group: 'Movimientos', render: () => <MovimientoTab tipo="FACTURAS_PEDIDOS" label="Facturas de pedidos" /> },
  { id: 'ingresos_facturas', label: 'Ingresos de facturas', group: 'Movimientos', render: () => <MovimientoTab tipo="INGRESOS_FACTURAS" label="Ingresos de facturas" /> },
];

export default function MaestrosPage() {
  return (
    <MotoredLayout>
      <MaestrosTabs tabs={TABS} />
    </MotoredLayout>
  );
}
