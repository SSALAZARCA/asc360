'use client';
/**
 * frontend/components/motored/MotoredSidebar.js
 *
 * Motored's OWN menu (sdd/motored-pedidos-cimientos, Phase 6, design
 * ADR-7). This is NOT `components/Sidebar.js` with relabeled items -- it is
 * a separate component with a genuinely distinct visual identity (cyan/slate
 * palette from `app/motored/layout.js`'s `.motored-theme`, square corners
 * instead of asc360's rounded "glass" card, no logo-fetch/company-branding
 * concerns since Motored has no per-tenant logo), per the user's explicit
 * request that Motored's menu look and feel different from asc360's.
 *
 * Reads/writes ONLY `motored_user`/`motored_token` -- never `um_user`/
 * `um_token`.
 */
import { useRouter, usePathname } from 'next/navigation';
import { LogOut, Warehouse, Users, ShieldCheck } from 'lucide-react';
import { MOTORED_TOKEN_KEY, MOTORED_USER_KEY } from '../../lib/motored/motoredFetch';

const ALL_ITEMS = [
  { id: 'maestros', name: 'Maestros', icon: Warehouse, path: '/motored/maestros' },
  { id: 'usuarios', name: 'Usuarios', icon: Users, path: '/motored/usuarios', adminOnly: true },
];

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
    <aside
      style={{
        width: '260px',
        minHeight: '100vh',
        background: 'var(--motored-surface, #101d2e)',
        borderRight: '1px solid var(--motored-border, rgba(148,197,255,0.12))',
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0,
      }}
    >
      <div style={{ padding: '1.75rem 1.5rem', borderBottom: '1px solid var(--motored-border, rgba(148,197,255,0.12))' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div
            style={{
              width: '2.75rem',
              height: '2.75rem',
              borderRadius: '0.5rem',
              background: 'var(--motored-primary, #22d3ee)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <ShieldCheck size={20} color="#0a1420" strokeWidth={2.5} />
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: '1rem', fontWeight: 800, color: 'var(--motored-text, #e6f4ff)', letterSpacing: '0.02em' }}>
              MOTORED
            </h1>
            <p style={{ margin: 0, fontSize: '0.625rem', fontWeight: 700, color: 'var(--motored-primary, #22d3ee)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              Pedidos
            </p>
          </div>
        </div>
      </div>

      <nav style={{ flex: 1, padding: '1rem 0.75rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname?.startsWith(item.path);
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => router.push(item.path)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
                padding: '0.75rem 1rem',
                borderRadius: '0.5rem',
                border: 'none',
                background: isActive ? 'var(--motored-surface-alt, #16273b)' : 'transparent',
                color: isActive ? 'var(--motored-primary, #22d3ee)' : 'var(--motored-text-muted, #7fa3c4)',
                fontSize: '0.8rem',
                fontWeight: 700,
                textAlign: 'left',
                cursor: 'pointer',
              }}
            >
              <Icon size={16} />
              {item.name}
            </button>
          );
        })}
      </nav>

      <div style={{ padding: '1rem 1.5rem', borderTop: '1px solid var(--motored-border, rgba(148,197,255,0.12))' }}>
        <p style={{ margin: '0 0 0.5rem', fontSize: '0.7rem', fontWeight: 700, color: 'var(--motored-text, #e6f4ff)' }}>
          {user?.nombre || 'Usuario'}
        </p>
        <button
          type="button"
          onClick={handleLogout}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            background: 'transparent',
            border: 'none',
            color: 'var(--motored-text-muted, #7fa3c4)',
            fontSize: '0.75rem',
            fontWeight: 700,
            cursor: 'pointer',
            padding: 0,
          }}
        >
          <LogOut size={14} /> Salir
        </button>
      </div>
    </aside>
  );
}
