'use client';
import { useState, useEffect } from 'react';
import AdminLayout from '../admin-layout';
import ImportsTabs from '../../components/imports/ImportsTabs';

export default function ImportsPage() {
  const [userRole, setUserRole] = useState(null);

  useEffect(() => {
    const stored = localStorage.getItem('um_user');
    if (stored) {
      const u = JSON.parse(stored);
      setUserRole(u.role);
    }
  }, []);

  return (
    <AdminLayout fullWidth>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', paddingBottom: '2rem' }}>
        <div>
          <h1 style={{ color: '#fff', fontWeight: 800, fontSize: '20px', margin: 0, letterSpacing: '-0.02em' }}>
            Estado de Pedidos
          </h1>
          <p style={{ color: '#606075', fontSize: '12px', margin: '4px 0 0' }}>
            Seguimiento de importaciones — motos y repuestos
          </p>
        </div>
        <ImportsTabs userRole={userRole} />
      </div>
    </AdminLayout>
  );
}
