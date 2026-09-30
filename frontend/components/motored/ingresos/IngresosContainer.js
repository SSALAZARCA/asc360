'use client';
/** ADMIN login log screen: filters + table + pagination. */
import useAdminGate from '../../../lib/motored/useAdminGate';
import DetractoresPagination from '../detractores/DetractoresPagination';
import { errorStyle } from '../detractores/styles';
import IngresosFilters from './IngresosFilters';
import IngresosTable from './IngresosTable';
import useIngresosList, { PAGE_SIZE } from './useIngresosList';

function ListBody({ list }) {
  const { data, loading, error, filters, setPage } = list;
  if (error) return <div role="alert" style={errorStyle}>{error}</div>;
  if (!data) return <p style={{ margin: 0, fontSize: '0.8rem' }}>Cargando...</p>;
  if (data.items.length === 0) {
    return <p style={{ margin: 0, fontSize: '0.8rem' }}>{loading ? 'Cargando...' : 'No hay ingresos con estos filtros.'}</p>;
  }
  return (
    <>
      <IngresosTable eventos={data.items} />
      <DetractoresPagination page={filters.page} pageSize={PAGE_SIZE} total={data.total} onChange={setPage} />
    </>
  );
}

export default function IngresosContainer() {
  const { allowed } = useAdminGate();
  const list = useIngresosList(allowed);
  if (!allowed) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '100%' }}>
      <h1 className="motored-h-pantalla">Registro de ingresos</h1>
      <IngresosFilters filters={list.filters} setFilter={list.setFilter} />
      <ListBody list={list} />
    </div>
  );
}
