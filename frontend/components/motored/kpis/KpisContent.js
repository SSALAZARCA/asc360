'use client';
/** "KPI's": header filters + tabs. ADMIN, COMPRAS and GERENCIA only (`useTableroGate`). */
import { useCallback, useMemo, useState } from 'react';
import useTableroGate from '../tablero-asesores/useTableroGate';
import { getAsesorDetalle, getComisiones, getTiendas, getVentas } from '../../../lib/motored/kpisApi';
import KpiFrescura from './KpiFrescura';
import KpiHeader from './KpiHeader';
import KpiTabs from './KpiTabs';
import { COLOR } from './tokens';
import useKpiFiltros from './useKpiFiltros';
import useAsesorOpciones from './useAsesorOpciones';
import useKpis from './useKpis';
import AsesorDetalle from './asesores/AsesorDetalle';
import ComisionesTab from './comisiones/ComisionesTab';
import TiendasTab from './tiendas/TiendasTab';
import VentasTab from './ventas/VentasTab';

const FETCHERS = {
  ventas: getVentas, tiendas: getTiendas, comisiones: getComisiones,
  asesor: (filtros) => getAsesorDetalle(filtros, filtros.asesor),
};
// The Asesores tab is ALWAYS the single-asesor view (`asesor`): there is no "everyone" view.
const TABS = { ventas: VentasTab, tiendas: TiendasTab, asesor: AsesorDetalle, comisiones: ComisionesTab };
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

function Pestana({ vista, kpis, filtros }) {
  if (kpis.error) return <Mensaje error>{kpis.error}</Mensaje>;
  if (!kpis.data) return <Esqueleto />;
  const Tab = TABS[vista];
  return <Tab data={kpis.data} filtros={filtros} />;
}

/** The asesor of the single view: the chosen one while she is among those who sold, else the best seller (first of the list). */
const asesorEfectivo = (lista, elegido) => (lista ? (lista.find((a) => a.cedula === elegido) ?? lista[0])?.cedula ?? null : null);

export default function KpisContent() {
  const allowed = useTableroGate();
  const [tab, setTab] = useState('ventas');
  const { opciones, filtros, cambiar, error } = useKpiFiltros(allowed);
  const enAsesores = tab === 'asesores';
  const asesores = useAsesorOpciones(allowed && enAsesores, filtros);
  const asesor = enAsesores ? asesorEfectivo(asesores, filtros.asesor) : null;
  const vista = enAsesores ? 'asesor' : tab;
  const filtrosVista = useMemo(() => ({ ...filtros, asesor }), [filtros, asesor]);
  // Without an asesor yet (options loading, or nobody sold) there is nothing to fetch.
  const kpis = useKpis(enAsesores && !asesor ? 'asesores' : vista, filtrosVista, FETCHERS);
  const seleccionar = useCallback((cedula) => cambiar({ asesor: cedula }), [cambiar]);
  if (!allowed) return null;
  const sinVentas = opciones && !opciones.ultimo_mes;
  const sinAsesores = enAsesores && asesores?.length === 0;
  return (
    <div style={{ fontFamily: 'var(--motored-font-kpi)', color: COLOR.ink, display: 'flex', flexDirection: 'column', gap: 22, maxWidth: 1240, minWidth: 0, overflowX: 'clip' }}>
      <KpiHeader opciones={opciones} filtros={filtros} onChange={cambiar} tab={tab} asesores={asesores} asesor={asesor} onAsesor={seleccionar} />
      <KpiTabs value={tab} onChange={setTab} />
      {error && <Mensaje error>{error}</Mensaje>}
      {opciones && !sinVentas && !sinAsesores && <KpiFrescura data={kpis.data} alRecalcular={kpis.recargar} />}
      {sinVentas && <Mensaje>Todavía no hay ventas cargadas.</Mensaje>}
      {!sinVentas && sinAsesores && <Mensaje>No hay asesores con venta en los filtros elegidos.</Mensaje>}
      {!sinVentas && !sinAsesores && opciones && <Pestana vista={vista} kpis={kpis} filtros={filtros} />}
    </div>
  );
}
