'use client';
/** Corridas screen: launch form + filters + table + paging + anular dialog. */
import { useCallback } from 'react';
import { useRouter } from 'next/navigation';
import usePedidosGate from '../../../lib/motored/usePedidosGate';
import { aPagina } from '../../../lib/motored/paginacion';
import DetractoresPagination from '../detractores/DetractoresPagination';
import useCorridas from './useCorridas';
import useLanzarCorrida from './useLanzarCorrida';
import useAnularCorrida from './useAnularCorrida';
import LanzarCorridaForm from './LanzarCorridaForm';
import CorridasFiltros from './CorridasFiltros';
import CorridasTable from './CorridasTable';
import AnularCorridaDialog from './AnularCorridaDialog';
import { errorStyle, mutedStyle } from './styles';

function Cuerpo({ list, onOpen, onAnular }) {
  const { data, loading, error, filters, setPage } = list;
  if (error) return <p role="alert" style={errorStyle}>{error}</p>;
  if (!data) return <p style={mutedStyle}>Cargando...</p>;
  if (data.items.length === 0) {
    return <p style={mutedStyle}>{loading ? 'Cargando...' : 'Sin pedidos para mostrar'}</p>;
  }
  const { pageSize, total } = aPagina(data);
  return (
    <>
      <CorridasTable corridas={data.items} onOpen={onOpen} onAnular={onAnular} onTerminal={list.reload} />
      <DetractoresPagination page={filters.page} pageSize={pageSize} total={total} onChange={setPage} />
    </>
  );
}

export default function CorridasContainer() {
  const router = useRouter();
  const allowed = usePedidosGate();
  const list = useCorridas(allowed);
  const lanzar = useLanzarCorrida(list.reload);
  const anular = useAnularCorrida(list.reload);
  const abrir = useCallback((id) => router.push(`/motored/pedidos/${id}`), [router]);
  if (!allowed) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '100%' }}>
      <h1 className="motored-h-pantalla">Pedidos</h1>
      <LanzarCorridaForm lanzar={lanzar} />
      <CorridasFiltros filters={list.filters} setFilter={list.setFilter} />
      <Cuerpo list={list} onOpen={abrir} onAnular={anular.abrir} />
      <AnularCorridaDialog anular={anular} />
    </div>
  );
}
