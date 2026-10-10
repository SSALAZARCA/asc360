'use client';
/** Header of the KPI's: title, subtitle and the three popover filters (Período, Punto de venta, HMCL). */
import { useCallback, useState } from 'react';
import { COLOR } from './tokens';
import AsesorFilter from './filtros/AsesorFilter';
import HmclFilter from './filtros/HmclFilter';
import PeriodoFilter from './filtros/PeriodoFilter';
import TiendasFilter from './filtros/TiendasFilter';

const SUBTITULO = 'Ventas, inventario y pedidos de la red · repuestos, accesorios, llantas, lubricantes, baterías, GPS y cascos';

/** `ocultarPeriodo` swaps the Período filter for the muted `etiquetaPeriodo` (tabs that do not depend on the months). `tab`, `asesores` (the options of the "Asesor" filter, null while loading), `asesor` (the one in force) and `onAsesor` are only needed to show that filter on the Asesores tab. */
export default function KpiHeader({ opciones, filtros, onChange, tab, asesores = null, asesor = null, onAsesor, ocultarPeriodo = false, etiquetaPeriodo = null }) {
  const [abierto, setAbierto] = useState(null);
  const cerrar = useCallback(() => setAbierto(null), []);
  const props = (id) => ({ abierto: abierto === id, onToggle: () => setAbierto((a) => (a === id ? null : id)), onClose: cerrar });
  return (
    <header style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-end', justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <h1 style={{ margin: 0, fontSize: 30, fontWeight: 700, letterSpacing: '-.02em' }}>KPI&apos;s</h1>
        <p style={{ margin: 0, fontSize: 14, color: COLOR.muted }}>{SUBTITULO}</p>
      </div>
      {opciones?.ultimo_mes && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'flex-end' }}>
          {ocultarPeriodo
            ? etiquetaPeriodo && <span style={{ fontSize: 13, color: COLOR.muted, minHeight: 36, display: 'inline-flex', alignItems: 'center' }}>{etiquetaPeriodo}</span>
            : <PeriodoFilter opciones={opciones} filtros={filtros} onChange={onChange} {...props('per')} />}
          <TiendasFilter opciones={opciones} filtros={filtros} onChange={onChange} {...props('pdv')} />
          <HmclFilter filtros={filtros} onChange={onChange} {...props('hm')} />
          {tab === 'asesores' && <AsesorFilter lista={asesores} elegido={asesor} opciones={opciones} filtros={filtros} onElegir={onAsesor} {...props('as')} />}
        </div>
      )}
    </header>
  );
}
