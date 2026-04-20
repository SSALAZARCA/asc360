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
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('sidebar_collapsed');
      if (saved !== null) return saved === 'true';
      return window.innerWidth <= 1024;
    }
    return false;
  });

  const handleToggle = (val) => {
    setCollapsed(val);
    localStorage.setItem('sidebar_collapsed', String(val));
  };

  useEffect(() => {
    const onResize = () => {
      const isTablet = window.innerWidth <= 1024;
      const saved = localStorage.getItem('sidebar_collapsed');
      if (saved === null) setCollapsed(isTablet);
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    routerRef.current = router;
  }, [router]);

  useEffect(() => {
    const checkAuth = () => {
      const r = routerRef.current;
      const stored = sessionStorage.getItem('um_user');
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

  const sidebarWidth = collapsed ? 72 : 280;
  const marginLeft = sidebarWidth + 28; // 24px left-6 + 4px gap

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar collapsed={collapsed} onToggle={handleToggle} />
      <main
        className="admin-main"
        style={{
          marginLeft: `${marginLeft}px`,
          flex: 1,
          padding: fullWidth ? '1.25rem 1.25rem 0' : '1.5rem 2rem',
          overflow: 'auto',
          minWidth: 0,
          display: 'flex',
          flexDirection: 'column',
          transition: 'margin-left 0.25s ease',
        }}
      >
        {children}
      </main>
    </div>
  );
}
