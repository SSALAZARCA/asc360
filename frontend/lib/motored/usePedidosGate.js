'use client';
/**
 * Gate for the Pedidos pages: ADMIN and COMPRAS only (decision F4-16). Any
 * other Motored role is sent back to Maestros (UX only; the backend answers
 * 403 on every /corridas route).
 */
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { MOTORED_USER_KEY } from './motoredFetch';
import { homePathFor } from './session';

export const PEDIDOS_ROLES = ['ADMIN', 'COMPRAS'];

function readRole() {
  try {
    return JSON.parse(sessionStorage.getItem(MOTORED_USER_KEY))?.role ?? null;
  } catch {
    return null;
  }
}

export default function usePedidosGate() {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    if (PEDIDOS_ROLES.includes(readRole())) {
      setAllowed(true);
      return;
    }
    router.push(homePathFor(readRole()));
  }, [router]);

  return allowed;
}
