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
 */
import { useRouter, usePathname } from 'next/navigation';
import Image from 'next/image';
import { LogOut, Warehouse, Users } from 'lucide-react';
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
        background: 'var(--motored-surface, #ffffff)',
        borderRight: '1px solid var(--motored-border, #e4e4e7)',
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0,
      }}
    >
      <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--motored-border, #e4e4e7)' }}>
        <Image src="/motored-logo.png" alt="Motored" width={130} height={42} />
        <p style={{ margin: '0.5rem 0 0', fontSize: '0.625rem', fontWeight: 700, color: 'var(--motored-primary, #e20714)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Pedidos
        </p>
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
                background: isActive ? 'var(--motored-surface-alt, #f4f4f5)' : 'transparent',
                color: isActive ? 'var(--motored-primary, #e20714)' : 'var(--motored-text-muted, #5a5a5a)',
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

      <div style={{ padding: '1rem 1.5rem', borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
        <p style={{ margin: '0 0 0.5rem', fontSize: '0.7rem', fontWeight: 700, color: 'var(--motored-text, #1a1a18)' }}>
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
            color: 'var(--motored-text-muted, #5a5a5a)',
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
