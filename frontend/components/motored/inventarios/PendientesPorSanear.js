'use client';
/**
 * "4. Pendientes por sanear" (WU15), on the start screen of a PROGRAMADO
 * conteo: the store's supplier invoices still to enter in the ERP and its
 * transfers still to receive, the dates of the loads they come from, and the
 * leader's "Verificado en el ERP" marks (this conteo only). Iniciar only
 * warns about them (see `useIniciarConteo`).
 */
import InfoTooltip from '../InfoTooltip';
import { fechaBogota, fechaHoraBogota } from '../../../lib/motored/fechas';
import { formatEntero, formatPesos } from './conteosFormato';
import { avisoStyle, cardStyle, errorStyle, h2Style, mutedStyle } from './estilos';
import PendientesTabla from './PendientesTabla';
import usePendientesConteo from './usePendientesConteo';

const AYUDA = 'Facturas del proveedor que la tienda aún no ingresó en el ERP y traslados que aún no recibió. '
  + 'Si se cuenta antes de sanearlos, el conteo mostrará diferencias que no son reales. '
  + '"Verificado en el ERP" solo aplica a este conteo; la fuente oficial sigue siendo la próxima carga de archivos.';
const ESTADO_FACTURA = { LLEGO: 'Ya llegó', NO_HA_LLEGADO: 'Aún no llega', SIN_CONFIRMAR: 'Sin confirmar' };
const ESTADO_TRASLADO = { RECIBIDO: 'Recibido', NO_HA_LLEGADO: 'No ha llegado', SIN_CONFIRMAR: 'Sin confirmar' };
const CARGAS = [
  ['facturas_pedidos', 'Facturas de pedidos'], ['ingresos_facturas', 'Ingresos de facturas'], ['traslados', 'Traslados'],
];

const COLUMNAS_FACTURA = [
  { titulo: 'Fecha', valor: (f) => fechaBogota(f.fecha) },
  { titulo: 'Valor', valor: (f) => formatPesos(f.valor) },
  { titulo: 'Refs.', valor: (f) => formatEntero(f.num_referencias) },
  { titulo: 'Estado', valor: (f) => ESTADO_FACTURA[f.estado_confirmacion] ?? f.estado_confirmacion },
];
const COLUMNAS_TRASLADO = [
  { titulo: 'Fecha', valor: (t) => fechaBogota(t.fecha) },
  { titulo: 'Sale → Llega', valor: (t) => `${t.sale || t.bodega_salida} → ${t.llega || t.bodega_entrada}` },
  { titulo: 'Refs.', valor: (t) => formatEntero(t.refs) },
  { titulo: 'Estado', valor: (t) => ESTADO_TRASLADO[t.estado_confirmacion] ?? t.estado_confirmacion },
];

function textoCarga(carga) {
  if (!carga) return 'sin cargar';
  const hasta = carga.periodo_hasta ? ` (hasta ${fechaBogota(carga.periodo_hasta)})` : '';
  return `${fechaHoraBogota(carga.fecha_carga)}${hasta}`;
}

function LineaCargas({ cargas, desde }) {
  const partes = CARGAS.map(([clave, nombre]) => `${nombre}: ${textoCarga(cargas?.[clave])}`);
  if (desde) partes.push(`facturas verificables desde ${fechaBogota(desde)}`);
  return <div style={{ ...mutedStyle, fontSize: '0.8rem' }}>{`Últimas cargas · ${partes.join(' · ')}`}</div>;
}

function Listas({ datos, puedeMarcar, pendientes }) {
  const comun = { puedeMarcar, ocupado: pendientes.ocupado, onCambiar: pendientes.cambiar };
  // Side by side (owner, 2026-10-10); they wrap one under the other when
  // the screen is too narrow for both.
  const lado = { flex: '1 1 460px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: '0.5rem' };
  return (
    <>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-start' }}>
        <div style={lado}>
          <PendientesTabla
            {...comun} titulo="Facturas por ingresar" tipo="FACTURA" primera="Factura"
            filas={datos.facturas.map((f) => ({ ...f, id: f.factura }))} columnas={COLUMNAS_FACTURA}
          />
        </div>
        <div style={lado}>
          <PendientesTabla
            {...comun} titulo="Traslados por recibir" tipo="TRASLADO" primera="Documento"
            filas={datos.traslados.map((t) => ({ ...t, id: t.documento }))} columnas={COLUMNAS_TRASLADO}
          />
        </div>
      </div>
      <div style={mutedStyle}>
        Conviene ingresar en el ERP estas facturas y recibir estos traslados antes de iniciar; si no, el conteo
        mostrará diferencias que no son reales.
      </div>
    </>
  );
}

export default function PendientesPorSanear({ conteo, permisos }) {
  const pendientes = usePendientesConteo(conteo.id, conteo.estado === 'PROGRAMADO');
  const { datos, error } = pendientes;
  const vacio = datos && datos.facturas.length === 0 && datos.traslados.length === 0;

  return (
    <section style={cardStyle} aria-label="Pendientes por sanear">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
        <h2 style={h2Style}>4. Pendientes por sanear</h2>
        <InfoTooltip text={AYUDA} />
      </div>
      {!datos && !error && <div style={mutedStyle}>Consultando pendientes…</div>}
      {vacio && <div style={avisoStyle('success')}>Sin pendientes para esta tienda</div>}
      {datos && !vacio && <Listas datos={datos} puedeMarcar={permisos.opera} pendientes={pendientes} />}
      {datos && <LineaCargas cargas={datos.cargas} desde={datos.verificable_desde} />}
      {error && <p role="alert" style={errorStyle}>{error}</p>}
    </section>
  );
}
