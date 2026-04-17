'use client';
import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import Sidebar from '../components/Sidebar';

export default function AdminLayout({ children, fullWidth = false }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const checkAuth = () => {
      const stored = localStorage.getItem('um_user');
      if (!stored) {
        if (pathname !== '/login') router.push('/login');
      } else {
        const u = JSON.parse(stored);
        setUser(u);
        
        // Bloquear acceso a páginas exclusivas según rol
        const superadminOnly = ['/tenants', '/users', '/', '/settings'];
        if (u.role !== 'superadmin' && superadminOnly.includes(pathname)) {
           router.push('/kanban');
           return;
        }

        // proveedor solo puede estar en /imports
        if (u.role === 'proveedor' && pathname !== '/imports') {
          router.push('/imports');
          return;
        }
      }
      setLoading(false);
    };
    
    checkAuth();
    window.addEventListener('storage', checkAuth);
    return () => window.removeEventListener('storage', checkAuth);
  }, [pathname, router]);

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
