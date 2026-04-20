'use client';
import KPISummary from '../components/KPISummary';
import AdminLayout from './admin-layout';
import { RefreshCw } from 'lucide-react';

export default function Dashboard() {
  return (
    <AdminLayout fullWidth>
      <div style={{ maxWidth: '100%' }}>

        <header className="page-header">
          <div>
            <h1 className="page-title">
              Centro de <span style={{ fontStyle: 'italic', color: 'var(--accent-orange)', WebkitTextFillColor: 'var(--accent-orange)' }}>Comando</span>
            </h1>
            <p className="page-subtitle">Inteligencia Operativa · Red UM Colombia</p>
          </div>
        </header>

        <KPISummary />
      </div>
    </AdminLayout>
  );
}
