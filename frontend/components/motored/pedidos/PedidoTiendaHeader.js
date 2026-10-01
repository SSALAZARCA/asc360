'use client';
/** Header of the pedido of one tienda: who, which corrida, the TIENDA state, its lifecycle actions, last event, envio. */
import InfoTooltip from '../InfoTooltip';
import MotoredIconAction from '../MotoredIconAction';
import AccionesTienda from './AccionesTienda';
import EstadoPedidoBadge, { ESTADO_PEDIDO_TEXTO } from './EstadoPedidoBadge';
import PruebaBadge from './PruebaBadge';
import { tiendaDeCabecera } from './acciones';
import { etiquetaEvento, fechaHora } from './formato';
import { fechaCorta } from './reglas';
import { mutedStyle } from './styles';

const SIC_TEXTO = 'SIC: código con el que HMCL identifica a la tienda.';
const NOTAS = {
  CERRADO: 'Pedido cerrado: reábralo para ajustar',
  ENVIADO: 'Pedido enviado: ya no se puede ajustar.',
};

function Dato({ titulo, children, ayuda }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
      <span style={mutedStyle}>{titulo}</span>{ayuda && <InfoTooltip text={ayuda} />}<span>{children}</span>
    </span>
  );
}

function Notas({ cab }) {
  const { ultimo_evento: evento, envio } = cab;
  const nota = cab.es_escenario ? 'Escenario de prueba: solo lectura.' : NOTAS[cab.estado_pedido];
  return (
    <>
      {nota && <p style={{ margin: 0, fontSize: '0.8rem', fontWeight: 600 }}>{nota}</p>}
      {envio && <span style={mutedStyle}>{`Orden ${envio.numero_orden} · ${fechaCorta(envio.fecha_envio)}`}</span>}
      {evento && (
        <span style={mutedStyle}>
          {`${etiquetaEvento(evento.evento)}${evento.usuario ? ` por ${evento.usuario}` : ''} · ${fechaHora(evento.creado_en)}`}
        </span>
      )}
    </>
  );
}

export default function PedidoTiendaHeader({ cabecera, onHistorial, ciclo }) {
  return (
    <header style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <h1 className="motored-h-pantalla">{cabecera.nombre}</h1>
        <span style={{ display: 'inline-flex', alignItems: 'center' }}>
          <EstadoPedidoBadge estado={cabecera.estado_pedido} />
          <InfoTooltip text={ESTADO_PEDIDO_TEXTO} />
        </span>
        {cabecera.es_escenario && <PruebaBadge />}
        <MotoredIconAction action="Historial" label="Historial del pedido" touch onClick={onHistorial} />
        {ciclo && <AccionesTienda tienda={tiendaDeCabecera(cabecera)} alAccionar={ciclo.alAccionar} ocupado={ciclo.ocupado} />}
      </div>
      <div style={{ display: 'flex', gap: '1.25rem', flexWrap: 'wrap', fontSize: '0.85rem' }}>
        <Dato titulo="SIC" ayuda={SIC_TEXTO}>{cabecera.sic || '—'}</Dato>
        <Dato titulo="Corte">{fechaCorta(cabecera.fecha_corte)}</Dato>
        <Dato titulo="Corrida">{cabecera.corrida_codigo}</Dato>
      </div>
      <Notas cab={cabecera} />
    </header>
  );
}
