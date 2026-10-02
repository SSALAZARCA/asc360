'use client';
/** Pedido of one tienda: header, totals, class summary, lines (editable while it is a draft) and the Historial panel. */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import usePedidosGate from '../../../lib/motored/usePedidosGate';
import usePedidoTienda from './usePedidoTienda';
import useTiendasCorrida from './useTiendasCorrida';
import useLineasPedido from './useLineasPedido';
import useEdicionLinea from './useEdicionLinea';
import useAccionesPedido from './useAccionesPedido';
import useTopePedido from './useTopePedido';
import AvisoPedido from './AvisoPedido';
import ConfirmarRecorteDialog from './ConfirmarRecorteDialog';
import DialogosPedido from './DialogosPedido';
import HistorialDrawer from './HistorialDrawer';
import LineasSeccion from './LineasSeccion';
import PedidoTiendaHeader from './PedidoTiendaHeader';
import ResumenClasesTable, { filasPorClase } from './ResumenClasesTable';
import TopeBanner from './TopeBanner';
import TotalesPedido from './TotalesPedido';
import { errorStyle, mutedStyle, volverStyle } from './styles';
import { mapaRecortes } from './tope';

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

function Detalle({ cabecera, corridaId, sucursalId, corrida, onHistorial, alCambiarPedido, recortes, refresco }) {
  const conLineas = cabecera.estado === 'OK';
  const lineas = useLineasPedido(corridaId, sucursalId, conLineas);
  const { parchear, recargar } = lineas;
  const edicion = useEdicionLinea({ corridaId, parchear, recargar, alCambiarPedido });
  const editable = Boolean(cabecera.acciones && cabecera.acciones.editar);
  // A recorte changes many lines at once: read the page again (filters and paging stay as they were).
  useEffect(() => { if (refresco > 0) recargar(); }, [refresco, recargar]);
  const filas = useMemo(
    () => filasPorClase(sucursalId, corrida?.resumen, corrida?.resumen_a_pedir),
    [sucursalId, corrida],
  );
  if (!conLineas) return <SinPedido cabecera={cabecera} />;
  return (
    <>
      <TotalesPedido totales={cabecera.totales} />
      <ResumenClasesTable filas={filas} />
      <LineasSeccion lineas={lineas} edicion={{ ...edicion, editable }} onHistorial={onHistorial} recortes={recortes} />
    </>
  );
}

export default function PedidoTiendaContainer({ corridaId, sucursalId }) {
  const router = useRouter();
  const allowed = usePedidosGate();
  const { cabecera, error, reload: recargarCabecera } = usePedidoTienda(corridaId, sucursalId, allowed);
  const { data: corrida, reload: recargarCorrida } = useTiendasCorrida(corridaId, allowed);
  // An edit changes the totals of the header and the class summary of the corrida.
  const recargarBase = useCallback(() => { recargarCabecera(); recargarCorrida(); }, [recargarCabecera, recargarCorrida]);
  const tope = useTopePedido({
    corridaId, sucursalId, estadoPedido: cabecera ? cabecera.estado_pedido : null, habilitado: allowed, recargarBase,
  });
  const { recorte, alCambiar: alCambiarPedido } = tope;
  const acciones = useAccionesPedido(corridaId, alCambiarPedido);
  const [historial, setHistorial] = useState(null);
  if (!allowed) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '100%' }}>
      <button type="button" className="motored-row-action" style={volverStyle} onClick={() => router.push(`/motored/pedidos/${corridaId}`)}>
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
          <AvisoPedido aviso={recorte.aviso} onDescartar={recorte.descartarAviso} />
          <TopeBanner
            propuesta={tope.propuesta} cerrado={tope.cerrado}
            puedeAplicar={Boolean(cabecera.acciones && cabecera.acciones.editar)} onAplicar={recorte.abrir}
          />
          <Detalle
            cabecera={cabecera} corridaId={corridaId} sucursalId={sucursalId} corrida={corrida}
            onHistorial={(linea) => setHistorial({ linea })} alCambiarPedido={alCambiarPedido}
            recortes={mapaRecortes(tope.propuesta)} refresco={tope.refresco}
          />
        </>
      )}
      {cabecera && <DialogosPedido acciones={acciones} corridaId={corridaId} fechaCorte={cabecera.fecha_corte} />}
      {cabecera && recorte.abierto && tope.propuesta && (
        <ConfirmarRecorteDialog
          nombre={cabecera.nombre} propuesta={tope.propuesta} actualizada={recorte.actualizada}
          ocupado={recorte.ocupado} error={recorte.error} onConfirm={recorte.confirmar} onCancel={recorte.cancelar}
        />
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
