'use client';
/** "KPI's": header filters + tabs. ADMIN, COMPRAS and GERENCIA only (`useTableroGate`). */
import { useState } from 'react';
import useTableroGate from '../tablero-asesores/useTableroGate';
import { getAsesores, getComisiones, getTiendas, getVentas } from '../../../lib/motored/kpisApi';
import KpiFrescura from './KpiFrescura';
import KpiHeader from './KpiHeader';
import KpiTabs from './KpiTabs';
import { COLOR } from './tokens';
import useKpiFiltros from './useKpiFiltros';
import useKpis from './useKpis';
import AsesoresTab from './asesores/AsesoresTab';
import ComisionesTab from './comisiones/ComisionesTab';
import TiendasTab from './tiendas/TiendasTab';
import VentasTab from './ventas/VentasTab';

const FETCHERS = { ventas: getVentas, tiendas: getTiendas, asesores: getAsesores, comisiones: getComisiones };
const TABS = { ventas: VentasTab, tiendas: TiendasTab, asesores: AsesoresTab, comisiones: ComisionesTab };
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

function Pestana({ tab, kpis, filtros }) {
  if (kpis.error) return <Mensaje error>{kpis.error}</Mensaje>;
  if (!kpis.data) return <Esqueleto />;
  const Tab = TABS[tab];
  return <Tab data={kpis.data} filtros={filtros} />;
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
      {opciones && !sinVentas && <KpiFrescura data={kpis.data} alRecalcular={kpis.recargar} />}
      {sinVentas ? <Mensaje>Todavía no hay ventas cargadas.</Mensaje> : opciones && <Pestana tab={tab} kpis={kpis} filtros={filtros} />}
    </div>
  );
}
