'use client';
/**
 * Live panel of an open conteo (prototype "Main", WU12): header, KPIs, the
 * differences table, and on the side the pairs, the pairs' access and the
 * close card. Refreshes every 15 s visible / 60 s hidden plus "Actualizar
 * ahora". GERENCIA reads everything with no action buttons.
 */
import { useState } from 'react';
import DialogoPedido from '../pedidos/DialogoPedido';
import usePanel from './usePanel';
import { parejasSinActividad } from './conteosFormato';
import PanelEncabezado from './PanelEncabezado';
import PanelKpis from './PanelKpis';
import DiferenciasTabla from './DiferenciasTabla';
import ParejasCard from './ParejasCard';
import AccesoResumen from './AccesoResumen';
import CierreCard from './CierreCard';
import AsignarReconteoDialog from './AsignarReconteoDialog';
import CerrarConteoDialog from './CerrarConteoDialog';
import { errorStyle, filaFlexStyle, mutedStyle, paginaStyle } from './estilos';

const TERMINAR = {
  titulo: 'Terminar primera vuelta',
  descripcion: 'El sistema calcula las diferencias contra la foto del inventario y crea los reconteos de las que pasan el umbral. '
    + 'Después de esto las parejas ya no registran lecturas de primera vuelta.',
  texto: 'Terminar primera vuelta',
};

function Aviso({ aviso }) {
  if (!aviso) return null;
  if (aviso.tipo === 'error') return <p role="alert" style={errorStyle}>{aviso.texto}</p>;
  return <p role="status" style={{ ...mutedStyle, margin: 0, fontSize: '0.875rem' }}>{aviso.texto}</p>;
}

export default function PanelVivo({ conteo, permisos, acceso, onVerAcceso, onCambioEstado }) {
  const panel = usePanel(conteo, onCambioEstado);
  // { titulo, descripcion, texto, accion } of the confirm dialog on screen.
  const [confirmacion, setConfirmacion] = useState(null);
  const [asignando, setAsignando] = useState(null);
  // The idle pairs at the moment the close was asked (null: no close dialog).
  const [cerrando, setCerrando] = useState(null);
  const opera = permisos.opera;
  const items = panel.diferencias?.items ?? [];

  const confirmar = async () => {
    const { accion } = confirmacion;
    setConfirmacion(null);
    await accion();
  };
  const pedirDesconectar = (sesion) => setConfirmacion({
    titulo: `Desconectar ${sesion.etiqueta}`,
    descripcion: 'La pareja sale del conteo. Sus lecturas quedan guardadas y puede volver a entrar con el código.',
    texto: 'Desconectar',
    accion: () => panel.acciones.desconectar(sesion.id),
  });

  return (
    <section style={paginaStyle}>
      <PanelEncabezado conteo={conteo} actualizado={panel.actualizado} onActualizar={panel.cargar} />
      <PanelKpis conteo={conteo} diferencias={panel.diferencias} sesiones={panel.sesiones} />
      <Aviso aviso={panel.aviso} />
      <div style={filaFlexStyle}>
        <DiferenciasTabla
          conteo={conteo} diferencias={panel.diferencias} opera={opera} ocupado={panel.ocupado}
          onPedir={panel.acciones.pedirReconteo} onCancelar={panel.acciones.cancelarReconteo}
          onAsignar={setAsignando} onRepartir={panel.acciones.repartir}
        />
        <div style={{ flex: '1 1 340px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <ParejasCard sesiones={panel.sesiones} items={items} opera={opera} onDesconectar={pedirDesconectar} />
          {opera && conteo.acceso && <AccesoResumen acceso={acceso} onVerAcceso={onVerAcceso} />}
          <CierreCard
            conteo={conteo} items={items} opera={opera} ocupado={panel.ocupado}
            onTerminarRonda={() => setConfirmacion({ ...TERMINAR, accion: panel.acciones.terminarRonda })}
            onCerrar={() => setCerrando(parejasSinActividad(panel.sesiones))} onDescargarAvance={panel.acciones.descargarAvance}
          />
        </div>
      </div>
      {confirmacion && (
        <DialogoPedido
          titulo={confirmacion.titulo} descripcion={<span>{confirmacion.descripcion}</span>}
          textoConfirmar={confirmacion.texto} ocupado={false}
          onConfirm={confirmar} onCancel={() => setConfirmacion(null)}
        />
      )}
      {asignando && (
        <AsignarReconteoDialog
          conteoId={conteo.id} fila={asignando} sesiones={panel.sesiones}
          onCancel={() => setAsignando(null)} onListo={() => { setAsignando(null); panel.cargar(); }}
        />
      )}
      {cerrando && (
        <CerrarConteoDialog
          conteoId={conteo.id} inactivas={cerrando} onCancel={() => setCerrando(null)} onCerrado={onCambioEstado}
        />
      )}
    </section>
  );
}
