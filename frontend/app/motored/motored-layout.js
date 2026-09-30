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
 * "Wrong role" here means a role string outside the 5 valid Motored roles
 * (ADMIN|COMPRAS|SUCURSAL|CONSULTA|SERVICIO_CLIENTE) -- e.g. a corrupted/forged session
 * value. All 5 real roles get past this gate (SERVICIO_CLIENTE is then kept
 * inside its survey pages by the allow-list redirect); per-screen role restriction
 * (like `/motored/usuarios` being ADMIN-only) is enforced by the page
 * itself, same division of responsibility as asc360's `admin-layout.js`
 * (route-level gate) vs `Sidebar.js` (menu-visibility) vs the backend
 * (real enforcement).
 */
import { useEffect, useState, useRef } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import MotoredSidebar from '../../components/motored/MotoredSidebar';
import MotoredTopBar from '../../components/motored/MotoredTopBar';
import useDrawerMenu from '../../components/motored/useDrawerMenu';
import { MOTORED_USER_KEY, MOTORED_TOKEN_KEY } from '../../lib/motored/motoredFetch';
import { MI_CUENTA_PATH } from '../../lib/motored/session';
import {
  ROLE_SERVICIO_CLIENTE, SURVEY_ADMIN_PATH, isServicioClientePath,
} from '../../lib/motored/servicioCliente';

const VALID_ROLES = ['ADMIN', 'COMPRAS', 'SUCURSAL', 'CONSULTA', ROLE_SERVICIO_CLIENTE];

export default function MotoredLayout({ children }) {
  const router = useRouter();
  const routerRef = useRef(router);
  const pathname = usePathname();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const { open, openMenu, closeMenu } = useDrawerMenu(pathname);

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

      // SERVICIO_CLIENTE only works inside the survey module (UX guard; the
      // backend answers 403 everywhere else). Never mount the other pages.
      if (u.role === ROLE_SERVICIO_CLIENTE && !isServicioClientePath(pathname)) {
        r.push(SURVEY_ADMIN_PATH);
        return;
      }

      // Pending password change: the account page is the only place to be.
      if (u.must_change_password && pathname !== MI_CUENTA_PATH) {
        r.push(MI_CUENTA_PATH);
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
    <div className="motored-shell" style={{ display: 'flex', minHeight: '100vh' }}>
      <MotoredSidebar user={user} open={open} onClose={closeMenu} />
      {open && <div className="motored-backdrop" data-testid="motored-backdrop" onClick={closeMenu} />}
      <div className="motored-content" style={{ flex: 1, minWidth: 0 }}>
        <MotoredTopBar onOpenMenu={openMenu} />
        <main className="motored-main" style={{ padding: '2rem', minWidth: 0 }}>{children}</main>
      </div>
    </div>
  );
}
