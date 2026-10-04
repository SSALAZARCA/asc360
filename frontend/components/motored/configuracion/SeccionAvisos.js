'use client';
/** Avisos tab: when and to whom the "data about to expire" notice goes out. */
import CamposDeSeccion from './CamposDeSeccion';

const AVISO = 'Avisos por Telegram cuando un dato del pedido está por vencerse. '
  + 'El cambio rige desde el mes elegido y se toma en el siguiente chequeo del sistema.';

const CAMPOS = [
  {
    clave: 'aviso_hora_vispera',
    etiqueta: 'Hora del aviso de víspera',
    ayuda: 'Hora (de Bogotá) a la que se avisa, el día anterior, que un dato vence mañana. Si el sistema estaba apagado a esa hora, el aviso sale al volver ese mismo día.',
  },
  {
    clave: 'aviso_hora_dia',
    etiqueta: 'Hora del aviso del día del vencimiento',
    ayuda: 'Hora (de Bogotá) a la que se avisa, el mismo día, que un dato vence hoy. Un aviso nunca se manda dos veces ni después de vencido.',
  },
  {
    clave: 'aviso_roles_destino',
    etiqueta: 'A quién se avisa',
    ayuda: 'Los roles que reciben el aviso. Sólo les llega a los usuarios activos que ya vincularon su Telegram.',
  },
];

export default function SeccionAvisos(props) {
  return <CamposDeSeccion {...props} aviso={AVISO} campos={CAMPOS} />;
}
