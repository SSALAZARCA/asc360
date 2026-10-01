'use client';
/** Pedido of one tienda (read-only): header, totals, class summary, lines and the Historial panel. */
import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import usePedidosGate from '../../../lib/motored/usePedidosGate';
import usePedidoTienda from './usePedidoTienda';
import useTiendasCorrida from './useTiendasCorrida';
import useLineasPedido from './useLineasPedido';
import HistorialDrawer from './HistorialDrawer';
import LineasSeccion from './LineasSeccion';
import PedidoTiendaHeader from './PedidoTiendaHeader';
import ResumenClasesTable, { filasPorClase } from './ResumenClasesTable';
import TotalesPedido from './TotalesPedido';
import { errorStyle, mutedStyle } from './styles';

function SinPedido({ cabecera }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <p style={{ margin: 0, fontWeight: 600 }}>Esta tienda no tiene pedido en esta corrida: su cálculo no terminó bien.</p>
      <p style={{ ...mutedStyle, margin: 0 }}>
        {[cabecera.mensaje, cabecera.codigo && `(${cabecera.codigo})`].filter(Boolean).join(' ')}
      </p>
    </div>
  );
}

function Detalle({ cabecera, corridaId, sucursalId, corrida, onHistorial }) {
  const conLineas = cabecera.estado === 'OK';
  const lineas = useLineasPedido(corridaId, sucursalId, conLineas);
  const filas = useMemo(
    () => filasPorClase(sucursalId, corrida?.resumen, corrida?.resumen_a_pedir),
    [sucursalId, corrida],
  );
  if (!conLineas) return <SinPedido cabecera={cabecera} />;
  return (
    <>
      <TotalesPedido totales={cabecera.totales} />
      <ResumenClasesTable filas={filas} />
      <LineasSeccion lineas={lineas} onHistorial={onHistorial} />
    </>
  );
}

export default function PedidoTiendaContainer({ corridaId, sucursalId }) {
  const router = useRouter();
  const allowed = usePedidosGate();
  const { cabecera, error } = usePedidoTienda(corridaId, sucursalId, allowed);
  const { data: corrida } = useTiendasCorrida(corridaId, allowed);
  const [historial, setHistorial] = useState(null);
  if (!allowed) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '100%' }}>
      <button type="button" className="motored-row-action" style={{ alignSelf: 'flex-start' }} onClick={() => router.push(`/motored/pedidos/${corridaId}`)}>
        ← Volver a la corrida
      </button>
      {error && <p role="alert" style={errorStyle}>{error}</p>}
      {!error && !cabecera && <p style={mutedStyle}>Cargando...</p>}
      {cabecera && (
        <>
          <PedidoTiendaHeader cabecera={cabecera} onHistorial={() => setHistorial({ linea: null })} />
          <Detalle
            cabecera={cabecera} corridaId={corridaId} sucursalId={sucursalId} corrida={corrida}
            onHistorial={(linea) => setHistorial({ linea })}
          />
        </>
      )}
      {historial && (
        <HistorialDrawer
          corridaId={corridaId} sucursalId={sucursalId} linea={historial.linea}
          onClose={() => setHistorial(null)}
        />
      )}
    </div>
  );
}
