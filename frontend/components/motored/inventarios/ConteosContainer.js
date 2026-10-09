'use client';
/**
 * "Inventarios > Conteos": placeholder while stage 1 of the inventory counts
 * is being built. Gate: ADMIN, LIDER_INVENTARIOS and GERENCIA only; any other
 * role is sent to its home (UX only; the backend answers 403).
 */
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { MOTORED_USER_KEY } from '../../../lib/motored/motoredFetch';
import { CONTEOS_ROLES, homePathFor } from '../../../lib/motored/session';

const sectionStyle = { padding: '1.5rem' };
const titleStyle = { margin: '0 0 0.5rem', fontSize: '1.25rem', color: 'var(--motored-text, #1a1a18)' };
const textStyle = { margin: 0, color: 'var(--motored-text-muted, #5a5a5a)' };

function readRole() {
  try {
    return JSON.parse(sessionStorage.getItem(MOTORED_USER_KEY))?.role ?? null;
  } catch {
    return null;
  }
}

export function useConteosGate() {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    const role = readRole();
    if (CONTEOS_ROLES.includes(role)) {
      setAllowed(true);
      return;
    }
    router.push(homePathFor(role));
  }, [router]);

  return allowed;
}

export default function ConteosContainer() {
  const allowed = useConteosGate();
  if (!allowed) return null;
  return (
    <section style={sectionStyle}>
      <h1 style={titleStyle}>Conteos de inventario</h1>
      <p style={textStyle}>Módulo en construcción.</p>
    </section>
  );
}
