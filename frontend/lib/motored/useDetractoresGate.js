'use client';
/**
 * Gate for the detractors pages: ADMIN and SERVICIO_CLIENTE only. Any other
 * Motored role is sent back to Maestros (UX only; the backend answers 403).
 */
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { MOTORED_USER_KEY } from './motoredFetch';

const ALLOWED_ROLES = ['ADMIN', 'SERVICIO_CLIENTE'];

function readRole() {
  try {
    return JSON.parse(sessionStorage.getItem(MOTORED_USER_KEY))?.role ?? null;
  } catch {
    return null;
  }
}

export default function useDetractoresGate() {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    if (ALLOWED_ROLES.includes(readRole())) {
      setAllowed(true);
      return;
    }
    router.push('/motored/maestros');
  }, [router]);

  return allowed;
}
