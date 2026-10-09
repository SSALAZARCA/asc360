'use client';
/**
 * "Gestión repuestos > Ingresos facturas": the invoices of pending orders
 * still to be received. Placeholder today; the panel content comes later.
 * Gate: ADMIN, COMPRAS, GERENCIA and COORDINADOR_REPUESTOS only; any other
 * role is sent to its home (UX only; the backend answers 403).
 */
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { MOTORED_USER_KEY } from '../../../lib/motored/motoredFetch';
import { GESTION_REPUESTOS_ROLES, homePathFor } from '../../../lib/motored/session';

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
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '100%' }}>
      <h1 className="motored-h-pantalla">Ingresos facturas</h1>
      <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Aquí verá las facturas de pedidos pendientes por ingresar.
      </p>
    </div>
  );
}
