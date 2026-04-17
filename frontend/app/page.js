'use client';
import KPISummary from '../components/KPISummary';
import AdminLayout from './admin-layout';
import { RefreshCw } from 'lucide-react';

export default function Dashboard() {
  return (
    <AdminLayout fullWidth>
      <div style={{ maxWidth: '100%' }}>

        {/* Header compacto */}
        <header style={{
          display: 'flex',
          alignItems: 'flex-end',
          justifyContent: 'space-between',
          gap: '1rem',
          marginBottom: '1rem',
          paddingBottom: '0.75rem',
          borderBottom: '1px solid rgba(255,255,255,0.05)',
          flexWrap: 'wrap',
        }}>
          <div>
            <h1 className="page-title">
              Centro de <span style={{ fontStyle: 'italic', color: 'var(--accent-orange)', WebkitTextFillColor: 'var(--accent-orange)' }}>Comando</span>
            </h1>
            <p style={{
              fontSize: '0.62rem',
              fontWeight: 700,
              color: 'rgba(255,255,255,0.3)',
              textTransform: 'uppercase',
              letterSpacing: '0.12em',
              margin: '0.2rem 0 0',
            }}>
              Inteligencia Operativa · Red UM Colombia
            </p>
          </div>
        </header>

        <KPISummary />
      </div>
    </AdminLayout>
  );
}
