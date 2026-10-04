'use client';
/**
 * frontend/components/motored/MotoredSidebar.js
 *
 * Motored's OWN menu (sdd/motored-pedidos-cimientos, Phase 6, design
 * ADR-7). This is NOT `components/Sidebar.js` with relabeled items -- it is
 * a separate component with a genuinely distinct visual identity, sourced
 * from Motored's real brand system (`app/motored/layout.js`'s
 * `.motored-theme`: rojo Motored on a light surface, not asc360's orange),
 * per the user's explicit request that Motored's menu look and feel
 * different from asc360's.
 *
 * Reads/writes ONLY `motored_user`/`motored_token` -- never `um_user`/
 * `um_token`.
 *
 * Structure verified against the real design system's "Artboard 4 ·
 * navegación y estructura" (screenshotted with a headless browser, since
 * the file itself can't be read as text): 240px width (not an approximation),
 * logo alone at the top, a small uppercase section label below it, and the
 * active item marked with a solid red LEFT BORDER + light pink background +
 * red text -- not a filled block, which is what this component originally
 * (incorrectly) used.
 *
 * The aside is sticky and exactly one viewport tall, so the footer (user
 * name + "Salir") stays on screen however long the page is; only the nav
 * area scrolls if it ever overflows.
 *
 * Below 1024px the aside turns into an off-canvas drawer (`.motored-sidebar`
 * / `.is-open` rules in the theme CSS, odd/motored-responsive-tablet); the
 * parent owns the open state and passes `open`/`onClose`.
 *
 * The standalone "Cargas" entry was REMOVED (sdd/motored-cargas-tipo-
 * declarado; proposal decision #2: "ONE screen" / design D5): uploading is
 * now one of the 10 grouped tabs inside "Maestros" (`MovimientoTab.js`),
 * not a separate menu item. `/motored/cargas` itself still resolves (it
 * redirects), so an old bookmark keeps working even without a nav entry.
 */
import { useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import Image from 'next/image';
import {
  LogOut, Warehouse, Users, TrendingDown, ClipboardCheck, MessageSquareWarning, KeyRound, History,
  UserCog, ChevronDown, ChevronRight, ShoppingCart, BarChart3, Settings,
} from 'lucide-react';
import { MOTORED_TOKEN_KEY, MOTORED_USER_KEY } from '../../lib/motored/motoredFetch';

const ALL_ITEMS = [
  // Pedidos (Fase 4, decision F4-16): ADMIN and COMPRAS only.
  { id: 'pedidos', name: 'Pedidos', icon: ShoppingCart, path: '/motored/pedidos', roles: ['ADMIN', 'COMPRAS'] },
  { id: 'tablero-asesores', name: 'Tablero asesores', icon: BarChart3, path: '/motored/tablero-asesores', roles: ['ADMIN', 'COMPRAS', 'GERENCIA'] },
  { id: 'maestros', name: 'Maestros', icon: Warehouse, path: '/motored/maestros' },
  // A group (`children`) is a collapsible header that always starts folded; a
  // click opens or closes it. While folded on one of its pages, the header is
  // marked as the current section.
  {
    id: 'usuarios', name: 'Usuarios', icon: Users, adminOnly: true,
    children: [
      { id: 'usuarios-gestion', name: 'Gestión de usuarios', icon: UserCog, path: '/motored/usuarios' },
      { id: 'ingresos', name: 'Registro de ingresos', icon: History, path: '/motored/ingresos' },
    ],
  },
  { id: 'ventas-perdidas', name: 'Ventas perdidas', icon: TrendingDown, path: '/motored/ventas-perdidas', adminOnly: true },
  // `excludeRoles` (optional) hides an item from those roles only; `roles` (optional) restricts an item to those roles; `adminOnly` and items
  // without either keep their original behaviour. SERVICIO_CLIENTE only ever
  // sees items that list it in `roles`.
  { id: 'encuesta-satisfaccion', name: 'Encuesta satisfacción', icon: ClipboardCheck, path: '/motored/encuesta-satisfaccion', roles: ['ADMIN', 'SERVICIO_CLIENTE'] },
  { id: 'detractores', name: 'Detractores', icon: MessageSquareWarning, path: '/motored/detractores', roles: ['ADMIN', 'SERVICIO_CLIENTE'] },
  { id: 'mi-cuenta', name: 'Cambiar mi contraseña', icon: KeyRound, path: '/motored/mi-cuenta', roles: ['ADMIN', 'COMPRAS', 'SUCURSAL', 'CONSULTA', 'SERVICIO_CLIENTE', 'GERENCIA'] },
  // Configuración (ADMIN only): every business-operation setting, edited from the app.
  { id: 'configuracion', name: 'Configuración', icon: Settings, path: '/motored/configuracion', roles: ['ADMIN'] },
];

const asideStyle = {
  width: '240px', position: 'sticky', top: 0, height: '100vh',
  background: 'var(--motored-surface, #ffffff)',
  borderRight: '1px solid var(--motored-border, #e4e4e7)',
  display: 'flex', flexDirection: 'column', flexShrink: 0,
};

const logoBoxStyle = { padding: '1.5rem', borderBottom: '1px solid var(--motored-border, #e4e4e7)' };
const navStyle = { flex: 1, minHeight: 0, overflowY: 'auto', padding: '1rem 0.75rem', display: 'flex', flexDirection: 'column', gap: '2px' };
const navLabelStyle = { margin: '0 0 0.5rem 0.75rem', color: 'var(--motored-text-soft, #8a8a8a)' };
const footerBoxStyle = { padding: '1rem 1.5rem', borderTop: '1px solid var(--motored-border, #e4e4e7)' };
const userNameStyle = { margin: '0 0 0.5rem', fontSize: '0.7rem', fontWeight: 700, color: 'var(--motored-text, #1a1a18)' };
const logoutBtnStyle = {
  display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'transparent', border: 'none',
  color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.75rem', fontWeight: 700, cursor: 'pointer', padding: 0,
};

function menuItemStyle(isActive) {
  return {
    display: 'flex', alignItems: 'center', gap: '0.75rem',
    padding: '0.6rem 1rem 0.6rem 0.8rem', borderRadius: '0 6px 6px 0', border: 'none',
    borderLeft: isActive ? '3px solid var(--motored-primary, #e20714)' : '3px solid transparent',
    background: isActive ? 'var(--motored-brand-soft, #fde8ea)' : 'transparent',
    color: isActive ? 'var(--motored-primary, #e20714)' : 'var(--motored-text-muted, #5a5a5a)',
    fontSize: '0.8rem', fontWeight: 600, textAlign: 'left', cursor: 'pointer',
  };
}

function MenuItem({ item, isActive, onNavigate, indent = false }) {
  const Icon = item.icon;
  const style = indent ? { ...menuItemStyle(isActive), paddingLeft: '2.2rem' } : menuItemStyle(isActive);
  return (
    <button type="button" onClick={() => onNavigate(item.path)} style={style}>
      <Icon size={16} />
      {item.name}
    </button>
  );
}

const isActivePath = (pathname, path) => Boolean(pathname?.startsWith(path));

function MenuGroup({ group, pathname, onNavigate }) {
  const childActive = group.children.some((child) => isActivePath(pathname, child.path));
  const [expanded, setExpanded] = useState(false);
  const Icon = group.icon;
  const Chevron = expanded ? ChevronDown : ChevronRight;
  return (
    <>
      <button
        type="button" aria-expanded={expanded} aria-current={childActive ? 'true' : undefined}
        onClick={() => setExpanded((open) => !open)}
        style={menuItemStyle(childActive && !expanded)}
      >
        <Icon size={16} />
        <span style={{ flex: 1 }}>{group.name}</span>
        <Chevron size={14} aria-hidden="true" />
      </button>
      {expanded && group.children.map((child) => (
        <MenuItem
          key={child.id} item={child} indent
          isActive={isActivePath(pathname, child.path)} onNavigate={onNavigate}
        />
      ))}
    </>
  );
}

/** The menu entries a user sees (also read by the Roles y permisos matrix). */
export function menuItemsFor(user) {
  return ALL_ITEMS.filter((item) => {
    if (user?.must_change_password) return item.id === 'mi-cuenta';
    if (item.excludeRoles?.includes(user?.role)) return false;
    if (item.roles) return item.roles.includes(user?.role);
    if (user?.role === 'SERVICIO_CLIENTE') return false;
    return !item.adminOnly || user?.role === 'ADMIN';
  });
}

export default function MotoredSidebar({ user, open = false, onClose }) {
  const router = useRouter();
  const pathname = usePathname();

  const menuItems = menuItemsFor(user);

  const navigate = (path) => {
    onClose?.();
    router.push(path);
  };

  const handleLogout = () => {
    sessionStorage.removeItem(MOTORED_USER_KEY);
    sessionStorage.removeItem(MOTORED_TOKEN_KEY);
    window.dispatchEvent(new Event('storage'));
    router.push('/motored/login');
  };

  return (
    <aside className={`motored-sidebar${open ? ' is-open' : ''}`} style={asideStyle}>
      <div style={logoBoxStyle}>
        <Image src="/motored-logo.png" alt="Motored" width={130} height={42} />
      </div>

      <nav style={navStyle}>
        <p className="motored-t-rotulo" style={navLabelStyle}>Pedidos Motored</p>
        {menuItems.map((item) => (item.children
          ? <MenuGroup key={item.id} group={item} pathname={pathname} onNavigate={navigate} />
          : <MenuItem key={item.id} item={item} isActive={isActivePath(pathname, item.path)} onNavigate={navigate} />
        ))}
      </nav>

      <div style={footerBoxStyle}>
        <p style={userNameStyle}>{user?.nombre || 'Usuario'}</p>
        <button type="button" onClick={handleLogout} style={logoutBtnStyle}>
          <LogOut size={14} /> Salir
        </button>
      </div>
    </aside>
  );
}
