'use client';
import { useEffect, useState, useRef } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import Sidebar from '../components/Sidebar';

export default function AdminLayout({ children, fullWidth = false }) {
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
      const stored = localStorage.getItem('um_user');
      if (!stored) {
        if (pathname !== '/login') r.push('/login');
        return;
      }
      const u = JSON.parse(stored);
      setUser(u);

      const superadminOnly = ['/tenants', '/users', '/settings'];
      const dashboardRoles = ['superadmin', 'administrativo'];

      if (u.role !== 'superadmin' && superadminOnly.includes(pathname)) {
        r.push('/kanban');
        return;
      }
      if (pathname === '/' && !dashboardRoles.includes(u.role)) {
        r.push('/kanban');
        return;
      }
      if (u.role === 'proveedor' && pathname !== '/imports') {
        r.push('/imports');
        return;
      }
      setLoading(false);
    };

    checkAuth();
    window.addEventListener('storage', checkAuth);
    return () => window.removeEventListener('storage', checkAuth);
  }, [pathname]);

  if (loading) return null; // Prevenir un flash rápido de contenido no autorizado
  if (!user && pathname !== '/login') return null;

  return (
    <div style={{
      display: 'flex',
      minHeight: '100vh',
    }}>
      <Sidebar />
      <main style={{
        marginLeft: '308px',   /* 280px sidebar + 28px gap */
        flex: 1,
        padding: fullWidth ? '1.25rem 1.25rem 0' : '1.5rem 2rem',
        overflow: 'hidden',
        minWidth: 0,
        display: 'flex',
        flexDirection: 'column',
      }}>
        {children}
      </main>
    </div>
  );
}
