'use client';
import { useState, useEffect } from 'react';
import AdminLayout from '../admin-layout';
import ImportsTabs from '../../components/imports/ImportsTabs';

export default function ImportsPage() {
  const [userRole, setUserRole] = useState(null);

  useEffect(() => {
    const stored = sessionStorage.getItem('um_user');
    if (stored) {
      const u = JSON.parse(stored);
      setUserRole(u.role);
    }
  }, []);

  return (
    <AdminLayout fullWidth>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', paddingBottom: '2rem' }}>
        <div>
          <h1 className="page-title">Estado de <span style={{ fontStyle: 'italic', color: 'var(--accent-orange)', WebkitTextFillColor: 'var(--accent-orange)' }}>Pedidos</span></h1>
          <p className="page-subtitle">Seguimiento de importaciones — motos y repuestos</p>
        </div>
        <ImportsTabs userRole={userRole} />
      </div>
    </AdminLayout>
  );
}
