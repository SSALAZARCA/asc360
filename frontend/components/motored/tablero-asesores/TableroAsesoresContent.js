'use client';
/** "Tablero de asesores": filters + warnings + table. ADMIN and COMPRAS only (usePedidosGate). */
import usePedidosGate from '../../../lib/motored/usePedidosGate';
import useTableroAsesores from './useTableroAsesores';
import TableroFilters from './TableroFilters';
import TableroAvisos from './TableroAvisos';
import TableroTable from './TableroTable';

const mutedStyle = { fontSize: '0.8rem', color: 'var(--motored-text-muted, #5a5a5a)' };
const errorStyle = { margin: 0, fontSize: '0.8rem', color: 'var(--motored-danger, #c0392b)' };

function Cuerpo({ data, loading }) {
  if (!data) return <p style={mutedStyle}>{loading ? 'Cargando...' : ''}</p>;
  if (data.filas.length === 0) return <p style={mutedStyle}>No hay ventas para el rango y el filtro elegidos.</p>;
  return (
    <>
      <TableroAvisos data={data} />
      <TableroTable filas={data.filas} total={data.total} meses={data.meses} />
    </>
  );
}

export default function TableroAsesoresContent() {
  const allowed = usePedidosGate();
  const { filtros, setFiltros, data, loading, error } = useTableroAsesores(allowed);
  if (!allowed) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '100%' }}>
      <h1 className="motored-h-pantalla">Tablero de asesores</h1>
      <TableroFilters filtros={filtros} setFiltros={setFiltros} />
      {error && <p style={errorStyle}>{error}</p>}
      {loading && data && <p style={mutedStyle}>Actualizando...</p>}
      <Cuerpo data={data} loading={loading} />
    </div>
  );
}
