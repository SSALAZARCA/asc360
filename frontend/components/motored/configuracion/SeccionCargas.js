'use client';
/** Cargas tab: the business rules the file loads read. */
import CamposDeSeccion from './CamposDeSeccion';

const AVISO = 'Reglas con las que se leen los archivos de carga. '
  + 'Cada carga usa el valor vigente en el momento de procesarla.';

const CAMPOS = [
  {
    clave: 'tipos_inventario_incluidos',
    etiqueta: 'Líneas de inventario que cuentan',
    ayuda: 'Las líneas de producto (columna «Tipo inventario» del archivo) que se incluyen al cargar ventas e inventario; las demás se ignoran. Si cambia esta lista, revise también las líneas comerciales de Indicadores.',
  },
  {
    clave: 'estados_backorder_vigentes',
    etiqueta: 'Estados de backorder vigentes',
    ayuda: 'Los estados de una línea de backorder que cuentan como pendiente de entrega. Las líneas con otro estado se ignoran.',
  },
  {
    clave: 'dias_ventana_ingresos',
    etiqueta: 'Ventana de ingresos (días)',
    ayuda: 'Cuántos días hacia atrás se miran los ingresos de mercancía para cruzarlos con las facturas del proveedor y decidir si algo sigue en tránsito. Va de 1 a 3650.',
  },
  {
    clave: 'tolerancia_ingreso_pct',
    etiqueta: 'Tolerancia de ingresos (%)',
    ayuda: 'Diferencia de valor, en porcentaje, que se acepta entre una factura del proveedor y sus ingresos para darla por recibida. 2 es un 2 %.',
  },
  {
    clave: 'periodo_tolerancia_pct',
    etiqueta: 'Tolerancia del período declarado (%)',
    ayuda: 'Porcentaje máximo de líneas de otro mes que se acepta al declarar el período de un archivo. Si se pasa, el archivo de ventas se rechaza entero. Va de 0 a 100.',
  },
  {
    clave: 'bodegas_excluidas',
    etiqueta: 'Bodegas que no son tiendas',
    ayuda: 'Códigos de bodega que no son tiendas (p. ej. bodega central o producto terminado). Sus líneas se ignoran al cargar ventas e inventario, sin marcar error. Una bodega que no esté aquí ni tenga tienda asignada sigue dando error.',
  },
];

export default function SeccionCargas(props) {
  return <CamposDeSeccion {...props} aviso={AVISO} campos={CAMPOS} />;
}
