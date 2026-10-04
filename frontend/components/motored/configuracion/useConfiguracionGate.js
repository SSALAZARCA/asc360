'use client';
/**
 * Gate of the Configuración page: ADMIN only (owner decision). Its own gate on
 * purpose: widening Pedidos or the dashboard must never widen the settings.
 * Any other Motored role is sent back to Maestros (UX only; the backend
 * answers 403 on every settings route).
 */
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { MOTORED_USER_KEY } from '../../../lib/motored/motoredFetch';

export const CONFIGURACION_ROLES = ['ADMIN'];

function readRole() {
  try {
    return JSON.parse(sessionStorage.getItem(MOTORED_USER_KEY))?.role ?? null;
  } catch {
    return null;
  }
}

export default function useConfiguracionGate() {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    if (CONFIGURACION_ROLES.includes(readRole())) {
      setAllowed(true);
      return;
    }
    router.push('/motored/maestros');
  }, [router]);

  return allowed;
}
