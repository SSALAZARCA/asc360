'use client';
/** Pedido of one tienda: header, totals, class summary, lines (editable while it is a draft) and the Historial panel. */
import { useCallback, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import usePedidosGate from '../../../lib/motored/usePedidosGate';
import usePedidoTienda from './usePedidoTienda';
import useTiendasCorrida from './useTiendasCorrida';
import useLineasPedido from './useLineasPedido';
import useEdicionLinea from './useEdicionLinea';
import useAccionesPedido from './useAccionesPedido';
import AvisoPedido from './AvisoPedido';
import DialogosPedido from './DialogosPedido';
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

function Detalle({ cabecera, corridaId, sucursalId, corrida, onHistorial, alCambiarPedido }) {
  const conLineas = cabecera.estado === 'OK';
  const lineas = useLineasPedido(corridaId, sucursalId, conLineas);
  const { parchear, recargar } = lineas;
  const edicion = useEdicionLinea({ corridaId, parchear, recargar, alCambiarPedido });
  const editable = Boolean(cabecera.acciones && cabecera.acciones.editar);
  const filas = useMemo(
    () => filasPorClase(sucursalId, corrida?.resumen, corrida?.resumen_a_pedir),
    [sucursalId, corrida],
  );
  if (!conLineas) return <SinPedido cabecera={cabecera} />;
  return (
    <>
      <TotalesPedido totales={cabecera.totales} />
      <ResumenClasesTable filas={filas} />
      <LineasSeccion lineas={lineas} edicion={{ ...edicion, editable }} onHistorial={onHistorial} />
    </>
  );
}

export default function PedidoTiendaContainer({ corridaId, sucursalId }) {
  const router = useRouter();
  const allowed = usePedidosGate();
  const { cabecera, error, reload: recargarCabecera } = usePedidoTienda(corridaId, sucursalId, allowed);
  const { data: corrida, reload: recargarCorrida } = useTiendasCorrida(corridaId, allowed);
  // An edit changes the totals of the header and the class summary of the corrida.
  const alCambiarPedido = useCallback(() => { recargarCabecera(); recargarCorrida(); }, [recargarCabecera, recargarCorrida]);
  const acciones = useAccionesPedido(corridaId, alCambiarPedido);
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
          <PedidoTiendaHeader
            cabecera={cabecera} onHistorial={() => setHistorial({ linea: null })}
            ciclo={{ alAccionar: acciones.alAccionar, ocupado: acciones.ocupado }}
          />
          <AvisoPedido aviso={acciones.aviso} onDescartar={acciones.descartarAviso} />
          <Detalle
            cabecera={cabecera} corridaId={corridaId} sucursalId={sucursalId} corrida={corrida}
            onHistorial={(linea) => setHistorial({ linea })} alCambiarPedido={alCambiarPedido}
          />
        </>
      )}
      {cabecera && <DialogosPedido acciones={acciones} corridaId={corridaId} fechaCorte={cabecera.fecha_corte} />}
      {historial && (
        <HistorialDrawer
          corridaId={corridaId} sucursalId={sucursalId} linea={historial.linea}
          onClose={() => setHistorial(null)}
        />
      )}
    </div>
  );
}
