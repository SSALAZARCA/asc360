'use client';
/**
 * The bare /motored address (a bookmark, a typed URL): sends the visitor to
 * where a fresh login would (Inicio, or the account page while a password
 * change is pending or for a role without screens), or to login without a
 * session.
 */
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { MOTORED_TOKEN_KEY, MOTORED_USER_KEY } from '../../lib/motored/motoredFetch';
import { landingPathFor } from '../../lib/motored/session';

function destino() {
  try {
    const token = sessionStorage.getItem(MOTORED_TOKEN_KEY);
    const user = JSON.parse(sessionStorage.getItem(MOTORED_USER_KEY) || 'null');
    return token && user?.role ? landingPathFor(user) : '/motored/login';
  } catch {
    return '/motored/login';
  }
}

export default function MotoredRaiz() {
  const router = useRouter();
  useEffect(() => {
    router.replace(destino());
  }, [router]);
  return null;
}
