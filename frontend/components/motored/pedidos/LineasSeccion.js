'use client';
/** Filters, line table and paging of one tienda pedido. */
import ReferenciasPaginador from '../maestros/ReferenciasPaginador';
import LineasFiltros from './LineasFiltros';
import LineasPedidoTable from './LineasPedidoTable';
import { TAMANOS_LINEAS } from './useLineasPedido';
import { errorStyle, mutedStyle } from './styles';

function Cuerpo({ lineas, edicion, onHistorial, recortes }) {
  const { data, loading, error } = lineas;
  if (error) return <p role="alert" style={errorStyle}>{error}</p>;
  if (!data) return <p style={mutedStyle}>Cargando líneas...</p>;
  if (data.items.length === 0) return <p style={mutedStyle}>{loading ? 'Cargando líneas...' : 'Sin pedidos para mostrar'}</p>;
  return <LineasPedidoTable lineas={data.items} edicion={edicion} onHistorial={onHistorial} recortes={recortes} />;
}

/** `edicion` is the `useEdicionLinea` result plus `editable`; without it the table is read-only. `recortes` marks the lines a recorte would cut. */
export default function LineasSeccion({ lineas, edicion, onHistorial, recortes }) {
  const { filters, setFilter, setPage, setPageSize, data } = lineas;
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <LineasFiltros filters={filters} setFilter={setFilter} />
      <Cuerpo lineas={lineas} edicion={edicion} onHistorial={onHistorial} recortes={recortes} />
      {data && data.items.length > 0 && (
        <ReferenciasPaginador
          page={filters.page} pageSize={filters.pageSize} total={data.total} sizes={TAMANOS_LINEAS} unidad="líneas"
          onPageChange={setPage} onPageSizeChange={setPageSize}
        />
      )}
    </section>
  );
}
