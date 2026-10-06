'use client';
/**
 * Comisiones tab: the commission rules the KPI tablero (Comisiones tab) reads
 * to pay each asesor. A key the server does not return yet is skipped.
 */
import { useMemo } from 'react';
import CamposDeSeccion from './CamposDeSeccion';

const AVISO = 'El tablero de KPI usa estas reglas para calcular la comisión de cada asesor en el mes liquidado.';

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
  {
    clave: 'comision_bono_umbral_pct',
    etiqueta: 'Cumplimiento mínimo para los bonos',
    ayuda: 'Los bonos por línea solo se activan si el asesor cumple al menos este porcentaje de su presupuesto total del mes (incluido: con 95 % justo ya califica).',
  },
  {
    clave: 'comision_lineas',
    etiqueta: 'Bonos por línea',
    ayuda: 'Si el asesor pasa el cumplimiento mínimo, gana el bono de una línea cuando la venta de esa línea es al menos el porcentaje meta de SU venta TOTAL del mes (incluidas las ventas a HMCL). Cada línea se puede apagar: una línea apagada no se paga. Los bonos se suman a la comisión.',
  },
];

const normalizar = (texto) => String(texto).trim().toUpperCase().normalize('NFD').replace(/[̀-ͯ]/g, '');

function lineasConfiguradas(data) {
  for (const seccion of data.secciones || []) {
    for (const grupo of seccion.grupos) {
      const spec = grupo.claves.find((c) => c.clave === 'lineas_comerciales');
      const valor = spec?.efectivo_global?.valor;
      if (Array.isArray(valor)) return valor.map(normalizar).filter(Boolean);
    }
  }
  return null;
}

/** Hands the configured lineas_comerciales to the comision_lineas editor (as `spec.lineas`). */
export function conLineasComerciales(data) {
  const lineas = data ? lineasConfiguradas(data) : null;
  if (!lineas) return data;
  const conLineas = (c) => (c.clave === 'comision_lineas' ? { ...c, lineas } : c);
  return {
    ...data,
    secciones: data.secciones.map((s) => ({
      ...s, grupos: s.grupos.map((g) => ({ ...g, claves: g.claves.map(conLineas) })),
    })),
  };
}

export default function SeccionComisiones({ data, ...props }) {
  // Memoised: a new spec object on every render would reset the field's draft.
  const datos = useMemo(() => conLineasComerciales(data), [data]);
  return <CamposDeSeccion {...props} data={datos} aviso={AVISO} campos={CAMPOS} />;
}
