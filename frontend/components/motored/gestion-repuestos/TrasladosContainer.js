'use client';
/**
 * "Gestión repuestos > Traslados": the pending transfers panel. Only ADMIN, COORDINADOR_REPUESTOS and
 * ANALISTA_ADMINISTRATIVO get the confirm buttons; COMPRAS and GERENCIA read. The gate is the one of Ingresos facturas
 * (UX only; the backend answers 403).
 */
import { MOTORED_USER_KEY } from '../../../lib/motored/motoredFetch';
import { puedeConfirmarRol } from '../kpis/asesores/pendientes';
import { useGestionRepuestosGate } from './IngresosFacturasContainer';
import TrasladosPanel from './TrasladosPanel';

function readRole() {
  try {
    return JSON.parse(sessionStorage.getItem(MOTORED_USER_KEY))?.role ?? null;
  } catch {
    return null;
  }
}

export default function TrasladosContainer() {
  const allowed = useGestionRepuestosGate();
  if (!allowed) return null;
  return <TrasladosPanel puedeConfirmar={puedeConfirmarRol(readRole())} />;
}
