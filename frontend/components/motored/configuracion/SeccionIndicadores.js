'use client';
/** Indicadores tab: what the tablero de asesores will read from the registry. */
import CamposDeSeccion from './CamposDeSeccion';

const AVISO = 'Se aplican cuando estén activos los indicadores de comisiones: '
  + 'hasta entonces el tablero sigue usando los valores de siempre.';

const CAMPOS = [
  {
    clave: 'hmcl_nits',
    etiqueta: 'NIT de HMCL',
    ayuda: 'NIT de las empresas del grupo HMCL (la fábrica de las motos). El tablero usa esta lista para saber qué ventas son de HMCL y poder incluirlas, excluirlas o verlas solas.',
  },
  {
    clave: 'grupo_por_cargo',
    etiqueta: 'Grupo de cada cargo',
    ayuda: 'Dice en qué grupo cuenta cada cargo en el tablero de asesores: Persona (se muestra uno por uno), Comerciales (se suman en un solo grupo) u Otros. Un cargo que no esté en la lista cuenta como Otros. Los nombres se escriben siempre en mayúsculas.',
  },
  {
    clave: 'lineas_comerciales',
    etiqueta: 'Líneas comerciales',
    ayuda: 'Las líneas de producto que cuentan como venta en el tablero (repuestos, accesorios, llantas...). Las demás no se cuentan. Deben ser líneas que la carga de inventario ya incluye en Cargas.',
  },
  {
    clave: 'kpi_semaforo_cortes',
    etiqueta: 'Colores del semáforo',
    ayuda: 'Desde qué porcentaje de cumplimiento un indicador se pinta verde y desde cuál ámbar. Por debajo del ámbar es rojo. El ámbar tiene que ser menor que el verde y ambos van entre 0 y 200.',
  },
];

export default function SeccionIndicadores(props) {
  return <CamposDeSeccion {...props} aviso={AVISO} campos={CAMPOS} />;
}
