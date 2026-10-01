'use client';
/**
 * "Consolidado" tab of the corrida detail: what the whole network orders,
 * references x tiendas (ADMIN and COMPRAS; the page gate already applies).
 * It is mounted only while the tab is open, so every visit reads fresh states.
 */
import DetractoresPagination from '../detractores/DetractoresPagination';
import { formatCOP } from '../../../lib/motored/formatCOP';
import ConsolidadoLeyenda from './ConsolidadoLeyenda';
import ConsolidadoMatrix from './ConsolidadoMatrix';
import useConsolidado from './useConsolidado';
import { sinPedido } from './ConsolidadoColumna';
import { plural, unidades } from './formato';
import { errorStyle, labelStyle, mutedStyle, resumenRedStyle } from './styles';

function ResumenRed({ data }) {
  const conPedido = data.tiendas.filter((t) => !sinPedido(t)).length;
  return (
    <div role="group" aria-label="Resumen de la red" style={resumenRedStyle}>
      <span>{conPedido} {plural(conPedido, 'tienda', 'tiendas')}</span>
      <span>{unidades(data.totales.unidades)} unidades</span>
      <span>{formatCOP(data.totales.valor)}</span>
    </div>
  );
}

function Buscador({ texto, onChange }) {
  return (
    <label style={labelStyle}>
      Buscar
      <input type="search" value={texto} placeholder="Código o nombre" style={{ minHeight: '44px' }} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

function Cuerpo({ consolidado }) {
  const { data, loading } = consolidado;
  if (!data) return <p style={mutedStyle}>{loading ? 'Cargando consolidado...' : null}</p>;
  if (data.filas.length === 0) return <p style={mutedStyle}>{loading ? 'Cargando consolidado...' : 'Sin pedidos para mostrar'}</p>;
  return (
    <>
      <ConsolidadoLeyenda tiendas={data.tiendas} />
      <ConsolidadoMatrix tiendas={data.tiendas} filas={data.filas} totales={data.totales} />
    </>
  );
}

export default function ConsolidadoContainer({ corridaId }) {
  const consolidado = useConsolidado(corridaId, true);
  const { data, error, texto, setTexto, page, setPage, pageSize } = consolidado;
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {data && data.filas.length > 0 && <ResumenRed data={data} />}
      <Buscador texto={texto} onChange={setTexto} />
      {error && <p role="alert" style={errorStyle}>{error}</p>}
      {!(error && !data) && <Cuerpo consolidado={consolidado} />}
      {data && data.total > 0 && (
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={mutedStyle}>{data.total} {plural(data.total, 'referencia', 'referencias')}</span>
          {data.total > pageSize && <DetractoresPagination page={page} pageSize={pageSize} total={data.total} onChange={setPage} />}
        </div>
      )}
    </section>
  );
}
