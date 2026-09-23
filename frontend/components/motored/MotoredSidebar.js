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
 * The standalone "Cargas" entry was REMOVED (sdd/motored-cargas-tipo-
 * declarado; proposal decision #2: "ONE screen" / design D5): uploading is
 * now one of the 10 grouped tabs inside "Maestros" (`MovimientoTab.js`),
 * not a separate menu item. `/motored/cargas` itself still resolves (it
 * redirects), so an old bookmark keeps working even without a nav entry.
 */
import { useRouter, usePathname } from 'next/navigation';
import Image from 'next/image';
import { LogOut, Warehouse, Users } from 'lucide-react';
import { MOTORED_TOKEN_KEY, MOTORED_USER_KEY } from '../../lib/motored/motoredFetch';

const ALL_ITEMS = [
  { id: 'maestros', name: 'Maestros', icon: Warehouse, path: '/motored/maestros' },
  { id: 'usuarios', name: 'Usuarios', icon: Users, path: '/motored/usuarios', adminOnly: true },
];

const asideStyle = {
  width: '240px', minHeight: '100vh',
  background: 'var(--motored-surface, #ffffff)',
  borderRight: '1px solid var(--motored-border, #e4e4e7)',
  display: 'flex', flexDirection: 'column', flexShrink: 0,
};

const logoBoxStyle = { padding: '1.5rem', borderBottom: '1px solid var(--motored-border, #e4e4e7)' };
const navStyle = { flex: 1, padding: '1rem 0.75rem', display: 'flex', flexDirection: 'column', gap: '2px' };
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

function MenuItem({ item, isActive, onNavigate }) {
  const Icon = item.icon;
  return (
    <button type="button" onClick={() => onNavigate(item.path)} style={menuItemStyle(isActive)}>
      <Icon size={16} />
      {item.name}
    </button>
  );
}

export default function MotoredSidebar({ user }) {
  const router = useRouter();
  const pathname = usePathname();

  const menuItems = ALL_ITEMS.filter((item) => !item.adminOnly || user?.role === 'ADMIN');

  const handleLogout = () => {
    sessionStorage.removeItem(MOTORED_USER_KEY);
    sessionStorage.removeItem(MOTORED_TOKEN_KEY);
    window.dispatchEvent(new Event('storage'));
    router.push('/motored/login');
  };

  return (
    <aside style={asideStyle}>
      <div style={logoBoxStyle}>
        <Image src="/motored-logo.png" alt="Motored" width={130} height={42} />
      </div>

      <nav style={navStyle}>
        <p className="motored-t-rotulo" style={navLabelStyle}>Pedidos Motored</p>
        {menuItems.map((item) => (
          <MenuItem key={item.id} item={item} isActive={pathname?.startsWith(item.path)} onNavigate={router.push} />
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
