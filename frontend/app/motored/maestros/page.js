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
 * The Bodegas tab is hidden (2026-10-03): bodegas are now managed from the
 * Sucursales upload, column "Bodegas secundarias" (their health warning, "bodega
 * sin sucursal", shows under Sucursales). `BodegasTab.js` stays in the repo.
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
import { Suspense, useEffect, useState } from 'react';
import MotoredLayout from '../motored-layout';
import MaestrosTabs from '../../../components/motored/maestros/MaestrosTabs';
import SucursalesTab from '../../../components/motored/maestros/SucursalesTab';
import ProveedoresTab from '../../../components/motored/maestros/ProveedoresTab';
import ReferenciasTab from '../../../components/motored/maestros/ReferenciasTab';
import ClientesTecniredTab from '../../../components/motored/maestros/ClientesTecniredTab';
import VendedoresTab from '../../../components/motored/maestros/VendedoresTab';
import MovimientoTab from '../../../components/motored/cargas/MovimientoTab';
import PresupuestosTab from '../../../components/motored/maestros/PresupuestosTab';
import { filtrarTabsPorRol } from '../../../lib/motored/maestrosTabsPorRol';
import { getRolActual } from '../../../lib/motored/motoredFetch';

const TABS = [
  { id: 'sucursales', label: 'Sucursales', group: 'Maestros', entidadSalud: 'sucursal', render: () => <SucursalesTab /> },
  { id: 'proveedores', label: 'Proveedores', group: 'Maestros', render: () => <ProveedoresTab /> },
  { id: 'referencias', label: 'Referencias', group: 'Maestros', entidadSalud: 'referencia', render: () => <ReferenciasTab /> },
  { id: 'clientes_tecnired', label: 'Clientes Tecnired', group: 'Maestros', render: () => <ClientesTecniredTab /> },
  { id: 'vendedores', label: 'Vendedores', group: 'Maestros', render: () => <VendedoresTab /> },
  { id: 'ventas', label: 'Ventas', group: 'Movimientos', render: () => <MovimientoTab tipo="VENTAS" label="Ventas" /> },
  { id: 'inventario', label: 'Inventario', group: 'Movimientos', render: () => <MovimientoTab tipo="INVENTARIO" label="Inventario" /> },
  { id: 'backorder', label: 'Backorder', group: 'Movimientos', render: () => <MovimientoTab tipo="BACKORDER" label="Backorder" /> },
  { id: 'demanda_perdida', label: 'Demanda perdida', group: 'Movimientos', render: () => <MovimientoTab tipo="DEMANDA_PERDIDA" label="Demanda perdida" /> },
  { id: 'facturas_pedidos', label: 'Facturas de pedidos', group: 'Movimientos', render: () => <MovimientoTab tipo="FACTURAS_PEDIDOS" label="Facturas de pedidos" /> },
  { id: 'ingresos_facturas', label: 'Ingresos de facturas', group: 'Movimientos', render: () => <MovimientoTab tipo="INGRESOS_FACTURAS" label="Ingresos de facturas" /> },
  { id: 'presupuestos', label: 'Presupuestos', group: 'Comercial', roles: ['ADMIN', 'GERENCIA'], render: () => <PresupuestosTab /> },
];

/** The role is read after mount (sessionStorage does not exist on the server). */
function MaestrosPorRol() {
  const [rol, setRol] = useState(undefined);
  useEffect(() => { setRol(getRolActual()); }, []);
  if (rol === undefined) return null;
  const tabs = filtrarTabsPorRol(TABS, rol);
  if (tabs.length === 0) return null;
  return <MaestrosTabs tabs={tabs} />;
}

export default function MaestrosPage() {
  return (
    <MotoredLayout>
      <Suspense fallback={null}>
        <MaestrosPorRol />
      </Suspense>
    </MotoredLayout>
  );
}
