'use client';
/** Limpieza tab: the automatic purges of old inventory and discarded corridas. */
import CamposDeSeccion from './CamposDeSeccion';

const AVISO = [
  'Nunca borra pedidos cerrados o enviados.',
  'Un cambio rige desde la próxima limpieza, nunca a mitad de una.',
];

const GRUPOS = [
  {
    titulo: 'Inventario',
    campos: [
      {
        clave: 'retencion_inventario_habilitada', etiqueta: 'Borrar inventario viejo automáticamente',
        ayuda: 'Encendido, el sistema borra una vez al día el inventario guardado más viejo que los días indicados. Apagado, no borra nada.',
      },
      {
        clave: 'retencion_inventario_dias', etiqueta: 'Días de inventario que se conservan',
        ayuda: 'Cuánto inventario se conserva, contado desde la carga de inventario más reciente (no desde hoy). Mínimo 30 días: menos borraría inventario que todavía se consulta.',
      },
    ],
  },
  {
    titulo: 'Corridas descartadas',
    campos: [
      {
        clave: 'retencion_corridas_habilitada', etiqueta: 'Borrar corridas descartadas automáticamente',
        ayuda: 'Encendido, el sistema borra una vez al día las corridas anuladas, fallidas o en borrador que ya pasaron los días indicados. Nunca borra una corrida cerrada ni una con pedidos cerrados o enviados.',
      },
      {
        clave: 'retencion_corridas_dias', etiqueta: 'Días que se conservan las corridas descartadas',
        ayuda: 'Cuántos días se guarda una corrida descartada antes de borrarla. Mínimo 7 días: menos borraría corridas recién descartadas.',
      },
    ],
  },
];

export default function SeccionLimpieza(props) {
  return <CamposDeSeccion {...props} aviso={AVISO} grupos={GRUPOS} />;
}
