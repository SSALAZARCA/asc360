'use client';
/** List screen: tabs + filters + table + pagination. */
import { useRouter } from 'next/navigation';
import useDetractoresGate from '../../../lib/motored/useDetractoresGate';
import useDetractoresList, { PAGE_SIZE } from './useDetractoresList';
import DetractoresTabs from './DetractoresTabs';
import DetractoresFilters from './DetractoresFilters';
import DetractoresTable from './DetractoresTable';
import DetractoresPagination from './DetractoresPagination';
import { errorStyle } from './styles';

function ListBody({ list, onOpen }) {
  const { data, loading, error, filters, setPage } = list;
  if (error) return <div role="alert" style={errorStyle}>{error}</div>;
  if (!data) return <p style={{ margin: 0, fontSize: '0.8rem' }}>Cargando...</p>;
  if (data.items.length === 0) {
    return <p style={{ margin: 0, fontSize: '0.8rem' }}>{loading ? 'Cargando...' : 'No hay casos con estos filtros.'}</p>;
  }
  return (
    <>
      <DetractoresTable casos={data.items} onOpen={onOpen} />
      <DetractoresPagination page={filters.page} pageSize={PAGE_SIZE} total={data.total} onChange={setPage} />
    </>
  );
}

export default function DetractoresContainer() {
  const router = useRouter();
  const allowed = useDetractoresGate();
  const list = useDetractoresList(allowed);
  if (!allowed) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '100%' }}>
      <h1 className="motored-h-pantalla">Detractores</h1>
      <DetractoresTabs value={list.filters.estado} conteo={list.data?.conteo_por_estado} onChange={(v) => list.setFilter('estado', v)} />
      <DetractoresFilters filters={list.filters} setFilter={list.setFilter} />
      <ListBody list={list} onOpen={(id) => router.push(`/motored/detractores/${id}`)} />
    </div>
  );
}
