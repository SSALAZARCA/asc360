'use client';
/**
 * "Gestión repuestos > Ingresos facturas": the pending invoices panel. Only
 * ADMIN, COORDINADOR_REPUESTOS and ANALISTA_ADMINISTRATIVO get the confirm buttons
 * (ADMIN and ANALISTA_ADMINISTRATIVO also the template download); the rest read.
 * Gate: ADMIN, COMPRAS, GERENCIA, COORDINADOR_REPUESTOS and ANALISTA_ADMINISTRATIVO only; any other
 * role is sent to its home (UX only; the backend answers 403).
 */
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { MOTORED_USER_KEY } from '../../../lib/motored/motoredFetch';
import { puedeConfirmarRol, puedeDescargarPlantillaRol } from '../kpis/asesores/pendientes';
import { GESTION_REPUESTOS_ROLES, homePathFor } from '../../../lib/motored/session';
import IngresosFacturasPanel from './IngresosFacturasPanel';

function readRole() {
  try {
    return JSON.parse(sessionStorage.getItem(MOTORED_USER_KEY))?.role ?? null;
  } catch {
    return null;
  }
}

export function useGestionRepuestosGate() {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    const role = readRole();
    if (GESTION_REPUESTOS_ROLES.includes(role)) {
      setAllowed(true);
      return;
    }
    router.push(homePathFor(role));
  }, [router]);

  return allowed;
}

export default function IngresosFacturasContainer() {
  const allowed = useGestionRepuestosGate();
  if (!allowed) return null;
  const role = readRole();
  return <IngresosFacturasPanel puedeConfirmar={puedeConfirmarRol(role)} puedeDescargar={puedeDescargarPlantillaRol(role)} />;
}
