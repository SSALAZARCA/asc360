'use client';
/**
 * "Comparar" tab of a scenario corrida: the scenario next to a real corrida of
 * the same corte (real | prueba | change per tienda and reference), the totals
 * and the tiendas that cannot be compared. It is mounted only while the tab is
 * open. The corrida detail already gates the page (ADMIN and COMPRAS).
 */
import { useState } from 'react';
import DetractoresPagination from '../detractores/DetractoresPagination';
import ComparacionTable from './ComparacionTable';
import ComparacionTotales, { ResumenComparacion } from './ComparacionTotales';
import PruebaBadge from './PruebaBadge';
import useComparacion from './useComparacion';
import useRealesComparables from './useRealesComparables';
import { resumenOverrides } from './escenario';
import { plural } from './formato';
import { fechaCorta } from './reglas';
import { errorStyle, labelStyle, mutedStyle, optionStyle } from './styles';

const regionStyle = {
  display: 'flex', flexDirection: 'column', gap: '0.75rem', padding: '1rem 1.25rem', minWidth: 0,
  background: 'var(--motored-surface, #ffffff)', border: '1px solid var(--motored-border, #e4e4e7)',
  borderRadius: 'var(--motored-radius-md, 8px)',
};
const checkStyle = { display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.8rem', minHeight: '44px' };

function Cabecera({ escenario, reales, con, onElegir }) {
  const probado = resumenOverrides(escenario.overrides);
  return (
    <section role="region" aria-label="Escenario frente a la corrida real" style={regionStyle}>
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <strong>{escenario.codigo}</strong>
        <PruebaBadge />
        <span style={mutedStyle}>frente a la corrida real</span>
        <label style={labelStyle}>
          Comparar con
          <select value={con} style={{ minHeight: '44px' }} onChange={(e) => onElegir(e.target.value)}>
            {reales.map((r) => (
              <option key={r.id} value={r.id} style={optionStyle}>{`${r.codigo} · ${fechaCorta(r.created_at)}`}</option>
            ))}
          </select>
        </label>
      </div>
      {probado.length > 0 && (
        <div style={{ fontSize: '0.8rem' }}>
          <span style={mutedStyle}>Parámetros probados</span>
          <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1.25rem' }}>
            {probado.map((linea) => <li key={linea}>{linea}</li>)}
          </ul>
        </div>
      )}
    </section>
  );
}

function Filtros({ filtros, setFiltro, totales }) {
  return (
    <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
      <label style={labelStyle}>
        Tienda
        <select value={filtros.sucursal} style={{ minHeight: '44px' }} onChange={(e) => setFiltro('sucursal', e.target.value)}>
          <option value="" style={optionStyle}>Todas</option>
          {totales.map((t) => <option key={t.sucursal_id} value={t.sucursal_id} style={optionStyle}>{t.nombre}</option>)}
        </select>
      </label>
      <label style={checkStyle}>
        <input type="checkbox" checked={filtros.soloDiferencias} onChange={(e) => setFiltro('soloDiferencias', e.target.checked)} />
        Solo con diferencias
      </label>
    </div>
  );
}

function NoComparables({ tiendas }) {
  if (tiendas.length === 0) return null;
  return (
    <div role="note" aria-label="Tiendas que no se comparan" style={{ ...regionStyle, fontSize: '0.8rem' }}>
      <strong>Tiendas que no se comparan</strong>
      <ul style={{ margin: 0, paddingLeft: '1.25rem' }}>
        {tiendas.map((t) => <li key={t.sucursal_id}>{`${t.nombre}: ${t.motivo}`}</li>)}
      </ul>
    </div>
  );
}

function Filas({ comparacion }) {
  const { data, loading, filtros } = comparacion;
  if (!data) return <p style={mutedStyle}>{loading ? 'Cargando comparación...' : null}</p>;
  if (data.filas.length === 0) {
    return <p style={mutedStyle}>{filtros.soloDiferencias ? 'Sin diferencias: el escenario pide lo mismo que la corrida real.' : 'Sin pedidos para mostrar'}</p>;
  }
  return <ComparacionTable filas={data.filas} />;
}

function Comparacion({ escenario, reales, con, onElegir }) {
  const comparacion = useComparacion(escenario.id, con);
  const { data, error, filtros, setFiltro, pageSize } = comparacion;
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <Cabecera escenario={escenario} reales={reales} con={con} onElegir={onElegir} />
      {error && <p role="alert" style={errorStyle}>{error}</p>}
      {data && (
        <>
          <ResumenComparacion totales={data.totales_por_sucursal} />
          <Filtros filtros={filtros} setFiltro={setFiltro} totales={data.totales_por_sucursal} />
        </>
      )}
      <h2 className="motored-h-seccion">Detalle por tienda y referencia</h2>
      <Filas comparacion={comparacion} />
      {data && data.total > 0 && (
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={mutedStyle}>{`${data.total} ${plural(data.total, 'fila', 'filas')}`}</span>
          {data.total > pageSize && <DetractoresPagination page={filtros.page} pageSize={pageSize} total={data.total} onChange={(p) => setFiltro('page', p)} />}
        </div>
      )}
      {data && (
        <>
          <h2 className="motored-h-seccion">Totales por tienda</h2>
          <ComparacionTotales totales={data.totales_por_sucursal} />
        </>
      )}
      {data && <NoComparables tiendas={data.no_comparables} />}
    </section>
  );
}

export default function ComparacionContainer({ escenario }) {
  const reales = useRealesComparables(escenario);
  const [elegida, setElegida] = useState('');
  if (reales.error) return <p role="alert" style={errorStyle}>{reales.error}</p>;
  if (!reales.items) return <p style={mutedStyle}>Cargando corridas reales...</p>;
  if (reales.items.length === 0) {
    return (
      <p style={mutedStyle}>
        {`No hay una corrida real calculada con la fecha de corte ${fechaCorta(escenario.fecha_corte)}. Calcule una corrida real con ese corte para poder comparar.`}
      </p>
    );
  }
  const con = reales.items.some((r) => r.id === elegida) ? elegida : reales.items[0].id;
  return <Comparacion escenario={escenario} reales={reales.items} con={con} onElegir={setElegida} />;
}
