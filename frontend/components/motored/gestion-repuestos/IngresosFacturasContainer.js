'use client';
/**
 * "Gestión repuestos > Ingresos facturas": the pending invoices panel. Only
 * COORDINADOR_REPUESTOS gets the confirm buttons; the rest read.
 * Gate: ADMIN, COMPRAS, GERENCIA and COORDINADOR_REPUESTOS only; any other
 * role is sent to its home (UX only; the backend answers 403).
 */
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { MOTORED_USER_KEY } from '../../../lib/motored/motoredFetch';
import { COORDINADOR_REPUESTOS, GESTION_REPUESTOS_ROLES, homePathFor } from '../../../lib/motored/session';
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
  return <IngresosFacturasPanel puedeConfirmar={readRole() === COORDINADOR_REPUESTOS} />;
}
