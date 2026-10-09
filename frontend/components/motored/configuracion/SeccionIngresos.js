'use client';
/**
 * Ingresos de facturas tab: how many references the store's asesor enters
 * by hand (above that the administrative analyst does it) and the fixed
 * values of the ERP "Entradas x Compra" template. Codes such as the supplier
 * branch keep their leading zeros ("001").
 */
import CamposDeSeccion from './CamposDeSeccion';

const AVISO = 'Estos valores se usan al descargar la plantilla del ERP; los descuentos se pueden ajustar luego en el Excel.';

const CAMPOS = [
  {
    clave: 'ingreso_umbral_referencias_asesor',
    etiqueta: 'Máximo de referencias que ingresa el asesor',
    ayuda: 'Una factura con hasta este número de referencias distintas (inclusive) la ingresa el asesor de repuestos de la tienda. Con más referencias la ingresa el analista administrativo.',
  },
  {
    clave: 'ingreso_plantilla_tipo_documento',
    etiqueta: 'Tipo de documento (ERP)',
    ayuda: 'Número del tipo de documento de Entradas x Compra en el ERP. Va en el encabezado de la plantilla.',
  },
  {
    clave: 'ingreso_plantilla_descuento_global',
    etiqueta: 'Descuento global %',
    ayuda: 'Porcentaje de descuento global del encabezado de la plantilla. La persona puede cambiarlo en el Excel antes de subirlo.',
  },
  {
    clave: 'ingreso_plantilla_proveedor_nit',
    etiqueta: 'NIT proveedor',
    ayuda: 'NIT del proveedor de las facturas de pedido (HMCL), sin puntos ni dígito de verificación.',
  },
  {
    clave: 'ingreso_plantilla_sucursal_proveedor',
    etiqueta: 'Sucursal del proveedor',
    ayuda: 'Código de la sucursal del proveedor en el ERP. Conserva los ceros a la izquierda, por ejemplo 001.',
  },
  {
    clave: 'ingreso_plantilla_comprador',
    etiqueta: 'Comprador (cédula)',
    ayuda: 'Cédula del comprador que figura en el encabezado de la plantilla.',
  },
  {
    clave: 'ingreso_plantilla_descuento_item',
    etiqueta: 'Descuento por ítem %',
    ayuda: 'Porcentaje de descuento que lleva cada línea de la plantilla. Normalmente 0.',
  },
  {
    clave: 'ingreso_plantilla_unidad_negocio',
    etiqueta: 'Unidad de negocio',
    ayuda: 'Código de la unidad de negocio de cada línea del ERP. Conserva los ceros a la izquierda, por ejemplo 003.',
  },
];

export default function SeccionIngresos(props) {
  return <CamposDeSeccion {...props} aviso={AVISO} campos={CAMPOS} />;
}
