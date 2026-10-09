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
 * "Wrong role" here means a role string outside the 6 valid Motored roles
 * (ADMIN|COMPRAS|SUCURSAL|CONSULTA|SERVICIO_CLIENTE|GERENCIA) -- e.g. a corrupted/forged session
 * value. All 6 real roles get past this gate (SERVICIO_CLIENTE is then kept
 * inside its survey pages and Inicio by the allow-list redirect); per-screen role restriction
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
import {
  COORDINADOR_REPUESTOS, INICIO_PATH, MI_CUENTA_PATH, ROLE_GERENCIA, homePathFor,
  isCoordinadorRepuestosPath, rolSinAcceso,
} from '../../lib/motored/session';
import { ROLE_SERVICIO_CLIENTE, isServicioClientePath } from '../../lib/motored/servicioCliente';

export const VALID_ROLES = [
  'ADMIN', 'COMPRAS', 'SUCURSAL', 'CONSULTA', ROLE_SERVICIO_CLIENTE, ROLE_GERENCIA, COORDINADOR_REPUESTOS,
];

/** The stored session user, or null when it is missing, unreadable or has
 * an unknown role. */
function leerUsuario(stored) {
  try {
    const u = JSON.parse(stored);
    return VALID_ROLES.includes(u?.role) ? u : null;
  } catch {
    return null;
  }
}

/** Where a signed-in user must go instead of `pathname`, or null to stay.
 * These are UX guards; the backend answers 403 everywhere else. */
function redireccionPara(u, pathname) {
  // SERVICIO_CLIENTE only works inside the survey module and Inicio.
  const scPermitido = isServicioClientePath(pathname) || pathname === INICIO_PATH;
  if (u.role === ROLE_SERVICIO_CLIENTE && !scPermitido) return homePathFor(u.role);
  // COORDINADOR_REPUESTOS only works inside the KPI's, "Gestión repuestos"
  // and its account page.
  if (u.role === COORDINADOR_REPUESTOS && !isCoordinadorRepuestosPath(pathname)) {
    return homePathFor(u.role);
  }
  // Pending password change, or a role with no screens yet (SUCURSAL/
  // CONSULTA, owner decision 2026-10-05): the account page is the only place.
  if ((u.must_change_password || rolSinAcceso(u.role)) && pathname !== MI_CUENTA_PATH) {
    return MI_CUENTA_PATH;
  }
  return null;
}

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

      const u = leerUsuario(stored);
      if (!u) {
        sessionStorage.removeItem(MOTORED_USER_KEY);
        sessionStorage.removeItem(MOTORED_TOKEN_KEY);
        r.push('/motored/login');
        return;
      }

      // Never mount a page the role cannot use: send it elsewhere instead.
      const destino = redireccionPara(u, pathname);
      if (destino) {
        r.push(destino);
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
