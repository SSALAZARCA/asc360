'use client';
/** "KPI's": header filters + tabs. ADMIN, COMPRAS and GERENCIA only (`useTableroGate`). */
import { useCallback, useEffect, useState } from 'react';
import useTableroGate from '../tablero-asesores/useTableroGate';
import { getAsesorDetalle, getAsesores, getComisiones, getTiendas, getVentas } from '../../../lib/motored/kpisApi';
import KpiFrescura from './KpiFrescura';
import KpiHeader from './KpiHeader';
import KpiTabs from './KpiTabs';
import { COLOR } from './tokens';
import useKpiFiltros from './useKpiFiltros';
import useAsesorOpciones from './useAsesorOpciones';
import useKpis from './useKpis';
import AsesorDetalle from './asesores/AsesorDetalle';
import AsesoresTab from './asesores/AsesoresTab';
import ComisionesTab from './comisiones/ComisionesTab';
import TiendasTab from './tiendas/TiendasTab';
import VentasTab from './ventas/VentasTab';

const FETCHERS = {
  ventas: getVentas, tiendas: getTiendas, asesores: getAsesores, comisiones: getComisiones,
  asesor: (filtros) => getAsesorDetalle(filtros, filtros.asesor),
};
// `asesor` is the Asesores tab with one asesor chosen in the header filter.
const TABS = { ventas: VentasTab, tiendas: TiendasTab, asesores: AsesoresTab, asesor: AsesorDetalle, comisiones: ComisionesTab };
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

function Pestana({ vista, kpis, filtros, onAsesor }) {
  if (kpis.error) return <Mensaje error>{kpis.error}</Mensaje>;
  if (!kpis.data) return <Esqueleto />;
  const Tab = TABS[vista];
  return <Tab data={kpis.data} filtros={filtros} onAsesor={onAsesor} />;
}

export default function KpisContent() {
  const allowed = useTableroGate();
  const [tab, setTab] = useState('ventas');
  const { opciones, filtros, cambiar, error } = useKpiFiltros(allowed);
  const vista = tab === 'asesores' && filtros.asesor ? 'asesor' : tab;
  const kpis = useKpis(vista, filtros, FETCHERS);
  const asesores = useAsesorOpciones(allowed && tab === 'asesores', filtros.sucursales);
  const seleccionar = useCallback((cedula) => cambiar({ asesor: cedula }), [cambiar]);
  // The asesor must belong to the chosen stores: when the list of the new stores leaves her out, back to everyone.
  useEffect(() => {
    if (filtros.asesor && asesores && !asesores.some((a) => a.cedula === filtros.asesor)) cambiar({ asesor: null });
  }, [asesores, filtros.asesor, cambiar]);
  if (!allowed) return null;
  const sinVentas = opciones && !opciones.ultimo_mes;
  return (
    <div style={{ fontFamily: 'var(--motored-font-kpi)', color: COLOR.ink, display: 'flex', flexDirection: 'column', gap: 22, maxWidth: 1240, minWidth: 0, overflowX: 'clip' }}>
      <KpiHeader opciones={opciones} filtros={filtros} onChange={cambiar} tab={tab} asesores={asesores} />
      <KpiTabs value={tab} onChange={setTab} />
      {error && <Mensaje error>{error}</Mensaje>}
      {opciones && !sinVentas && <KpiFrescura data={kpis.data} alRecalcular={kpis.recargar} />}
      {sinVentas ? <Mensaje>Todavía no hay ventas cargadas.</Mensaje> : opciones && <Pestana vista={vista} kpis={kpis} filtros={filtros} onAsesor={seleccionar} />}
    </div>
  );
}
