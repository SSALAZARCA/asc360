'use client';
/**
 * frontend/app/motored/motored-layout.js
 *
 * Motored's own route-guard component (sdd/motored-pedidos-cimientos,
 * Phase 6, task 6.2). Mirrors `app/admin-layout.js`'s SHAPE only (read
 * session -> redirect if unauthenticated/wrong-role -> render sidebar +
 * children when authorized, re-check on the `storage` event so a 401 from
 * `motoredFetch` clearing the session mid-session bounces the user out) --
 * it reads `motored_user`, never `um_user`, and redirects to
 * `/motored/login`, never `/login`.
 *
 * "Wrong role" here means a role string outside the 4 valid Motored roles
 * (ADMIN|COMPRAS|SUCURSAL|CONSULTA) -- e.g. a corrupted/forged session
 * value. All 4 real roles get past this gate; per-screen role restriction
 * (like `/motored/usuarios` being ADMIN-only) is enforced by the page
 * itself, same division of responsibility as asc360's `admin-layout.js`
 * (route-level gate) vs `Sidebar.js` (menu-visibility) vs the backend
 * (real enforcement).
 */
import { useEffect, useState, useRef } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import MotoredSidebar from '../../components/motored/MotoredSidebar';
import { MOTORED_USER_KEY, MOTORED_TOKEN_KEY } from '../../lib/motored/motoredFetch';

const VALID_ROLES = ['ADMIN', 'COMPRAS', 'SUCURSAL', 'CONSULTA'];

export default function MotoredLayout({ children }) {
  const router = useRouter();
  const routerRef = useRef(router);
  const pathname = usePathname();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    routerRef.current = router;
  }, [router]);

  useEffect(() => {
    const checkAuth = () => {
      const r = routerRef.current;
      const stored = sessionStorage.getItem(MOTORED_USER_KEY);

      if (!stored) {
        if (pathname !== '/motored/login') r.push('/motored/login');
        return;
      }

      let u;
      try {
        u = JSON.parse(stored);
      } catch {
        sessionStorage.removeItem(MOTORED_USER_KEY);
        sessionStorage.removeItem(MOTORED_TOKEN_KEY);
        r.push('/motored/login');
        return;
      }

      if (!VALID_ROLES.includes(u?.role)) {
        sessionStorage.removeItem(MOTORED_USER_KEY);
        sessionStorage.removeItem(MOTORED_TOKEN_KEY);
        r.push('/motored/login');
        return;
      }

      setUser(u);
      setLoading(false);
    };

    checkAuth();
    window.addEventListener('storage', checkAuth);
    return () => window.removeEventListener('storage', checkAuth);
  }, [pathname]);

  // Nunca renderizar contenido protegido mientras se resuelve/redirige --
  // ni siquiera brevemente (task 6.5's exact requirement).
  if (loading) return null;
  if (!user) return null;

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <MotoredSidebar user={user} />
      <main style={{ flex: 1, padding: '2rem', minWidth: 0 }}>{children}</main>
    </div>
  );
}
