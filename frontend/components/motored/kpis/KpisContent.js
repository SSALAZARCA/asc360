'use client';
/** "KPI's": header filters + tabs. ADMIN, COMPRAS and GERENCIA only (`useTableroGate`). */
import { useState } from 'react';
import useTableroGate from '../tablero-asesores/useTableroGate';
import TableroAsesoresContent from '../tablero-asesores/TableroAsesoresContent';
import { getVentas } from '../../../lib/motored/kpisApi';
import KpiHeader from './KpiHeader';
import KpiTabs from './KpiTabs';
import ProximamenteCard from './ProximamenteCard';
import { COLOR } from './tokens';
import useKpiFiltros from './useKpiFiltros';
import useKpis from './useKpis';
import VentasTab from './ventas/VentasTab';

// Only Ventas reads the new endpoints for now; Asesores keeps the legacy table until its own tab.
const FETCHERS = { ventas: getVentas };
const SOMBRA = { background: COLOR.track, borderRadius: 14, height: 120 };

function Esqueleto() {
  return (
    <div role="status" aria-label="Cargando" style={{ display: 'grid', gap: 16 }}>
      <div style={SOMBRA} />
      <div style={{ ...SOMBRA, height: 160 }} />
    </div>
  );
}

function Mensaje({ children, error = false }) {
  return <p role={error ? 'alert' : undefined} style={{ margin: 0, fontSize: 14, color: error ? 'var(--motored-danger, #C0392B)' : COLOR.muted }}>{children}</p>;
}

function Pestana({ tab, kpis }) {
  if (tab === 'tiendas') return <ProximamenteCard titulo="Tiendas" />;
  if (tab === 'asesores') return <TableroAsesoresContent embedded />;
  if (kpis.error) return <Mensaje error>{kpis.error}</Mensaje>;
  if (!kpis.data) return <Esqueleto />;
  return <VentasTab data={kpis.data} />;
}

export default function KpisContent() {
  const allowed = useTableroGate();
  const [tab, setTab] = useState('ventas');
  const { opciones, filtros, cambiar, error } = useKpiFiltros(allowed);
  const kpis = useKpis(tab, filtros, FETCHERS);
  if (!allowed) return null;
  const sinVentas = opciones && !opciones.ultimo_mes;
  return (
    <div style={{ fontFamily: 'var(--motored-font-kpi)', color: COLOR.ink, display: 'flex', flexDirection: 'column', gap: 22, maxWidth: 1240, minWidth: 0, overflowX: 'clip' }}>
      <KpiHeader opciones={opciones} filtros={filtros} onChange={cambiar} />
      <KpiTabs value={tab} onChange={setTab} />
      {error && <Mensaje error>{error}</Mensaje>}
      {sinVentas ? <Mensaje>Todavía no hay ventas cargadas.</Mensaje> : opciones && <Pestana tab={tab} kpis={kpis} />}
    </div>
  );
}
