/**
 * UI copy of the public pair counting screen (neutral Spanish, "usted").
 * Kept in one place so the screens match the approved prototypes.
 */
export const TEXTOS = {
  avisoDatos: 'Sus datos solo se usan para saber quién contó cada referencia. No se crea un usuario.',
  accesoInvalido: 'Código o enlace no válidos.',
  bloqueado: 'Demasiados intentos. Espere unos minutos e intente de nuevo.',
  sinConexionIngreso: 'Sin conexión. Revise el internet e intente de nuevo.',
  sesionTerminada: 'Su sesión de conteo terminó. Vuelva a ingresar con el código del conteo.',
  salida: 'Salió del conteo. Sus lecturas quedaron guardadas.',
  sinUbicacion: 'Primero indique la ubicación: escanee la etiqueta del estante o escriba su código.',
  rondaTerminada: 'La ronda de conteo terminó. Solo se cuentan los reconteos asignados: elija uno en "Reconteos asignados".',
  ayudaEscaner: 'Cada lectura suma 1. Escanee una ubicación para cambiar de estante.',
  notaCiega: 'Conteo a ciegas: no se muestra cuánto dice el sistema. Toque una fila para corregir la cantidad.',
  ubicacionInvalida: 'Escriba o escanee un código de ubicación de 1 a 30 caracteres.',
  pendientesSalir: 'Hay lecturas sin enviar. Espere a tener conexión antes de salir.',
  pendientesTerminar: 'Hay lecturas sin enviar. Espere a tener conexión para terminar el reconteo.',
  listaSinCargar: 'No se pudo cargar lo contado. Reintentando… No vuelva a escanear lo que ya contó.',
  sinCamara:
    'Este celular no permite escanear con la cámara. Escriba el código o conecte un lector Bluetooth: funciona como un teclado.',
};

const MOTIVOS = {
  RONDA_CERRADA: 'La ronda de conteo ya terminó',
  RECONTEO_NO_ASIGNADO: 'El reconteo ya no está asignado a esta pareja',
  RECONTEO_OTRO_CODIGO: 'El código no corresponde al reconteo',
  CODIGO_INVALIDO: 'Código inválido',
  CANTIDAD_INVALIDA: 'Cantidad inválida',
  ES_UBICACION: 'Es una etiqueta de ubicación',
  UBICACION_INACTIVA: 'La ubicación está desactivada',
  UBICACION_INVALIDA: 'Código de ubicación inválido',
  UBICACION_CHOCA_REFERENCIA: 'El código de ubicación se confunde con una referencia',
  LECTURA_NO_ENCONTRADA: 'No se pudo corregir: la lectura no existe',
};

export function textoMotivo(motivo) {
  return MOTIVOS[motivo] || 'No se pudo registrar';
}

/** Two or more master codes share the scanned code's key. */
export function textoAmbiguo(codigos) {
  const lista = codigos.length > 1
    ? `${codigos.slice(0, -1).join(', ')} y ${codigos[codigos.length - 1]}` : codigos.join('');
  return `Código ambiguo: coincide con ${lista}. Escríbalo exactamente como en el maestro.`;
}

export function textoPendientes(n) {
  return n === 1 ? '1 lectura pendiente de enviar' : `${n} lecturas pendientes de enviar`;
}

export function textoReferencias(n) {
  return n === 1 ? '1 referencia' : `${n} referencias`;
}

/** "hace 2 s", "hace 3 min" for the last reading. */
export function textoHace(desdeMs, ahoraMs) {
  const s = Math.max(0, Math.round((ahoraMs - desdeMs) / 1000));
  if (s < 60) return `hace ${s} s`;
  return `hace ${Math.floor(s / 60)} min`;
}

/** Quantities come as numbers or decimal strings ("4.00"). */
export function formatoCantidad(valor) {
  const n = Number(valor);
  return Number.isFinite(n) ? String(n) : '0';
}
