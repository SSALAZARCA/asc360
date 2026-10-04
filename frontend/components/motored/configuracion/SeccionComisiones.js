'use client';
/** Comisiones tab: the commission rules (not read by anything yet). */
import CamposDeSeccion from './CamposDeSeccion';

const AVISO = 'Se aplican cuando estén activos los indicadores de comisiones.';

const CAMPOS = [
  {
    clave: 'comision_tramos',
    etiqueta: 'Tramos de comisión',
    ayuda: 'Escalones de comisión según el cumplimiento de la meta. Cada tramo tiene un nombre, el porcentaje de cumplimiento desde el que aplica y la tasa de comisión. El primero empieza en 0 % y los siguientes van de menor a mayor. Use las flechas para reordenar.',
  },
  {
    clave: 'comision_base_pago',
    etiqueta: 'Base para pagar la comisión',
    ayuda: 'Si la comisión se calcula sobre la venta sin contar las ventas a HMCL o contándolas.',
  },
  {
    clave: 'cumplimiento_base',
    etiqueta: 'Base del cumplimiento',
    ayuda: 'Si el porcentaje de cumplimiento de la meta se mide contando las ventas a HMCL o sin contarlas.',
  },
  {
    clave: 'comision_cargos_asesor',
    etiqueta: 'Cargos que comisionan',
    ayuda: 'Los cargos que reciben comisión como asesores. Los nombres se escriben en mayúsculas, igual que en el maestro de personas.',
  },
];

export default function SeccionComisiones(props) {
  return <CamposDeSeccion {...props} aviso={AVISO} campos={CAMPOS} />;
}
