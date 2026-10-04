'use client';
/**
 * Gate of the "Tablero de asesores": ADMIN, COMPRAS and GERENCIA only (owner
 * decisions 2026-10-01 and 2026-10-04). It is its own gate on purpose: Pedidos and the dashboard are
 * separate decisions, so widening one must never widen the other. Any other
 * Motored role is sent back to Maestros (UX only; the backend answers 403).
 */
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { MOTORED_USER_KEY } from '../../../lib/motored/motoredFetch';

export const TABLERO_ROLES = ['ADMIN', 'COMPRAS', 'GERENCIA'];

function readRole() {
  try {
    return JSON.parse(sessionStorage.getItem(MOTORED_USER_KEY))?.role ?? null;
  } catch {
    return null;
  }
}

export default function useTableroGate() {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    if (TABLERO_ROLES.includes(readRole())) {
      setAllowed(true);
      return;
    }
    router.push('/motored/maestros');
  }, [router]);

  return allowed;
}
