'use client';
import { useRouter, usePathname } from 'next/navigation';

const NAV_ITEMS = [
  { path: '/tg/home',      label: 'Órdenes',   icon: '◉', roles: ['superadmin','jefe_taller','technician'] },
  { path: '/tg/vehicle',   label: 'Hoja Vida', icon: '⌖', roles: ['superadmin','jefe_taller','technician'] },
  { path: '/tg/parts',     label: 'Repuestos', icon: '⚙', roles: ['superadmin','jefe_taller','technician'] },
  { path: '/tg/otp',       label: 'OTP',       icon: '✎', roles: ['superadmin','jefe_taller','technician'] },
  { path: '/tg/reception', label: 'Recepción', icon: '+', roles: ['superadmin','jefe_taller','technician'] },
  { path: '/tg/admin',     label: 'Admin',     icon: '⬡', roles: ['superadmin'] },
];

export default function TgNav({ userRole }) {
  const router   = useRouter();
  const pathname = usePathname();
  const items    = NAV_ITEMS.filter(n => n.roles.includes(userRole));

  return (
    <nav style={{
      position: 'fixed', bottom: 0, left: 0, right: 0,
      background: '#13131a',
      borderTop: '1px solid rgba(255,255,255,0.06)',
      display: 'flex', justifyContent: 'space-around', alignItems: 'center',
      padding: '0.5rem 0 calc(0.6rem + env(safe-area-inset-bottom))',
      zIndex: 20,
    }}>
      {items.map(item => {
        const active = pathname === item.path;
        return (
          <button
            key={item.path}
            onClick={() => router.push(item.path)}
            style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3,
              background: 'none', border: 'none', cursor: 'pointer',
              color: active ? '#ff5f33' : '#606075',
              minWidth: 44, padding: '0.2rem 0.4rem',
              transition: 'color 0.15s',
              WebkitTapHighlightColor: 'transparent',
            }}
          >
            <span style={{ fontSize: '1rem', lineHeight: 1, fontWeight: active ? 900 : 400 }}>{item.icon}</span>
            <span style={{ fontSize: '0.48rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
