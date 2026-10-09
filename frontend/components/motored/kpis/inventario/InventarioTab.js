'use client';
/** Inventario tab, in the approved design's order: corte chip + Excel, six cards, trend + age, lines, stores, idle + stockouts. */
import { useState } from 'react';
import { descargarInventarioExcel } from '../../../../lib/motored/kpisApi';
import { COLOR } from '../tokens';
import AgotadasConDemanda from './AgotadasConDemanda';
import AntiguedadInventario from './AntiguedadInventario';
import { textoCorte } from './datos';
import { CSS_INVENTARIO } from './estilos';
import InventarioPorLinea from './InventarioPorLinea';
import InventarioPorTienda from './InventarioPorTienda';
import SinMovimiento from './SinMovimiento';
import TarjetasInventario from './TarjetasInventario';
import TendenciaInventario from './TendenciaInventario';

const TIP_CORTE = 'El inventario se toma del último corte cargado; ventas y costo de los últimos 3 meses';

function BotonExcel({ data, filtros }) {
  const [estado, setEstado] = useState({ ocupado: false, error: null });
  const descargar = async () => {
    setEstado({ ocupado: true, error: null });
    try {
      await descargarInventarioExcel(filtros, data.corte);
      setEstado({ ocupado: false, error: null });
    } catch {
      setEstado({ ocupado: false, error: 'No pudimos descargar el Excel. Intentá de nuevo.' });
    }
  };
  return (
    <>
      <button
        type="button" onClick={descargar} disabled={estado.ocupado} title="Descarga el inventario del último corte con su costo."
        style={{ appearance: 'none', border: `1px solid ${COLOR.line}`, background: COLOR.surface, color: COLOR.ink, fontFamily: 'inherit', fontSize: 12.5, fontWeight: 700, minHeight: 36, padding: '0 12px', borderRadius: 10, cursor: estado.ocupado ? 'default' : 'pointer', opacity: estado.ocupado ? 0.6 : 1 }}
      >
        {estado.ocupado ? 'Descargando…' : 'Descargar Excel'}
      </button>
      {estado.error && <p role="alert" style={{ flexBasis: '100%', margin: 0, fontSize: 12.5, color: 'var(--motored-danger, #C0392B)' }}>{estado.error}</p>}
    </>
  );
}

function Cabecera({ data, filtros }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', justifyContent: 'space-between' }}>
      <span data-testid="chip-corte" title={TIP_CORTE} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12.5, fontWeight: 500, color: COLOR.ink2, background: COLOR.surface, border: `1px solid ${COLOR.track}`, borderRadius: 999, padding: '6px 12px' }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></svg>
        {textoCorte(data)}
      </span>
      <BotonExcel data={data} filtros={filtros} />
    </div>
  );
}

export default function InventarioTab({ data, filtros, onChange }) {
  if (!data.corte) return <p style={{ margin: 0, fontSize: 14, color: COLOR.muted }}>Todavía no hay inventario cargado con costo.</p>;
  return (
    <section aria-label="Inventario" style={{ display: 'flex', flexDirection: 'column', gap: 18, minWidth: 0 }}>
      <style>{CSS_INVENTARIO}</style>
      <Cabecera data={data} filtros={filtros} />
      <TarjetasInventario data={data} />
      <div className="inv-row">
        <TendenciaInventario data={data} />
        <AntiguedadInventario data={data} />
      </div>
      <InventarioPorLinea data={data} />
      <InventarioPorTienda data={data} onChange={onChange} />
      <div className="inv-half">
        <SinMovimiento data={data} />
        <AgotadasConDemanda data={data} />
      </div>
    </section>
  );
}
