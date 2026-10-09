'use client';
/**
 * Conteos de inventario tab: the money amounts that send a referencia to
 * reconteo or mark it critical, and the maximum age of the Maestros
 * inventory when a count starts. The "reconteo below crítico" rule spans
 * two keys, so it is checked here against the other key's value in force
 * before saving.
 */
import { useMemo } from 'react';
import CamposDeSeccion from './CamposDeSeccion';
import { guardarParametro } from '../../../lib/motored/configuracionApi';

const RECONTEO = 'conteo_umbral_reconteo_pesos';
const CRITICO = 'conteo_umbral_critico_pesos';

const AVISO = 'Estos valores se copian en cada conteo al iniciarlo: un cambio aquí no altera los conteos que ya están en curso.';

const CAMPOS = [
  {
    clave: RECONTEO,
    etiqueta: 'Diferencia que pide reconteo',
    ayuda: 'Al terminar la primera ronda, toda referencia cuya diferencia valorizada (unidades de diferencia por el costo unitario) supere este monto en pesos pasa a reconteo, hecho por otra pareja. Debe ser menor que la diferencia crítica.',
  },
  {
    clave: CRITICO,
    etiqueta: 'Diferencia crítica',
    ayuda: 'Una referencia cuya diferencia valorizada supere este monto en pesos aparece en rojo y arriba en el panel del conteo, en vivo. Debe ser mayor que la diferencia que pide reconteo.',
  },
  {
    clave: 'conteo_inventario_vigencia_horas',
    etiqueta: 'Antigüedad máxima del inventario',
    ayuda: 'Al iniciar un conteo, si el último inventario de la tienda cargado en Maestros tiene más horas que este número, el sistema avisa y pide confirmar antes de contar contra ese inventario.',
  },
];

const pesos = (n) => `$ ${Number(n).toLocaleString('es-CO')}`;

function valorVigente(data, clave) {
  for (const seccion of (data && data.secciones) || []) {
    for (const grupo of seccion.grupos) {
      const spec = grupo.claves.find((c) => c.clave === clave);
      if (spec) return spec.efectivo_global?.valor;
    }
  }
  return undefined;
}

/** The Spanish error when the pair would break "reconteo < crítico", else null. */
export function errorUmbrales(clave, valor, data) {
  if (clave !== RECONTEO && clave !== CRITICO) return null;
  const otra = clave === RECONTEO ? CRITICO : RECONTEO;
  const actual = valorVigente(data, otra);
  if (actual === undefined || actual === null) return null;
  const [reconteo, critico] = clave === RECONTEO ? [valor, actual] : [actual, valor];
  if (Number(reconteo) < Number(critico)) return null;
  return `La diferencia que pide reconteo (${pesos(reconteo)}) debe ser menor que la diferencia crítica (${pesos(critico)}).`;
}

export default function SeccionConteos({ data, onGuardar = guardarParametro, ...props }) {
  const guardar = useMemo(() => async (payload) => {
    const error = errorUmbrales(payload.clave, payload.valor, data);
    if (error) throw new Error(error);
    return onGuardar(payload);
  }, [data, onGuardar]);
  return <CamposDeSeccion {...props} data={data} aviso={AVISO} campos={CAMPOS} onGuardar={guardar} />;
}
