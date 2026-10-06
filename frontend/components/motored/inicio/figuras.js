/**
 * Inicio: the four stat boxes built from `GET /api/motored/inicio`. Pure:
 * each figure becomes `{ id, titulo, subtitulo, valor, ayuda }`, with
 * `valor` null when the backend could not compute it (or the request
 * failed, `datos` null).
 */
import { formatCOP } from '../../../lib/motored/formatCOP';

const MESES = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
];
const ENTERO = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 0 });
const LINEAS = 'Total de las líneas comerciales (repuestos, accesorios, llantas, '
  + 'lubricantes, baterías, GPS y cascos)';
const TODAS = 'todas las tiendas.';
const IGUAL_MES = 'Es la misma venta que muestra KPIs.';
const IGUAL_ANIO = 'Es la misma venta del "Año corrido" de KPIs.';
const IGUAL_ASESORES = 'los mismos que cuenta KPIs › Asesores.';

const mayuscula = (texto) => texto.charAt(0).toUpperCase() + texto.slice(1);

/** "2026-09" -> { nombre: "septiembre", anio: "2026" }; null if unknown. */
function partes(aaaaMm) {
  const [anio, mes] = String(aaaaMm || '').split('-');
  const nombre = MESES[Number(mes) - 1];
  return nombre ? { nombre, anio } : null;
}

/** "2026-09" -> "septiembre de 2026" / "Septiembre 2026"; null if unknown. */
function mesDe(aaaaMm) {
  const p = partes(aaaaMm);
  if (!p) return null;
  return { largo: `${p.nombre} de ${p.anio}`, corto: `${mayuscula(p.nombre)} ${p.anio}` };
}

/** January..`hasta` -> subtitle and tooltip phrase; one month reads as that month. */
function rangoDe(desde, hasta) {
  const inicio = partes(desde);
  const fin = partes(hasta);
  if (!inicio || !fin) return null;
  if (desde === hasta) return { corto: mesDe(hasta).corto, frase: `en ${mesDe(hasta).largo}` };
  return {
    corto: `${mayuscula(inicio.nombre)} a ${fin.nombre} ${fin.anio}`,
    frase: `de ${inicio.nombre} a ${fin.nombre} de ${fin.anio}`,
  };
}

const disponible = (figura) => Boolean(figura?.disponible);

function ventasMes(figura) {
  const mes = disponible(figura) ? mesDe(figura.mes) : null;
  const periodo = mes ? `en ${mes.largo}` : 'del último mes completo';
  return {
    id: 'ventas_mes',
    titulo: 'Ventas del último mes',
    subtitulo: mes?.corto ?? null,
    valor: mes ? formatCOP(figura.valor) : null,
    ayuda: `${LINEAS} ${periodo}, ${TODAS} ${IGUAL_MES}`,
  };
}

function ventasAnio(figura) {
  const ok = disponible(figura);
  const rango = ok ? rangoDe(figura.desde, figura.hasta) : null;
  const periodo = rango?.frase ?? 'de enero al último mes con ventas';
  return {
    id: 'ventas_anio',
    titulo: 'Ventas acumuladas del año',
    subtitulo: rango?.corto ?? null,
    valor: ok ? formatCOP(figura.valor) : null,
    ayuda: `${LINEAS} ${periodo}, ${TODAS} ${IGUAL_ANIO}`,
  };
}

function conteo(id, titulo, ayuda, figura, subtitulo = null) {
  return {
    id, titulo, ayuda, subtitulo,
    valor: disponible(figura) ? ENTERO.format(figura.cantidad) : null,
  };
}

function asesores(figura) {
  const mes = disponible(figura) ? partes(figura.mes) : null;
  const periodo = mes ? `en ${mes.nombre} de ${mes.anio}` : 'en el último mes completo';
  return conteo(
    'asesores', 'Asesores', `Asesores con venta ${periodo}, ${IGUAL_ASESORES}`, figura,
    mes ? `Con ventas en ${mes.nombre} ${mes.anio}` : null,
  );
}

export function figurasDe(datos) {
  return [
    ventasMes(datos?.ventas_mes),
    ventasAnio(datos?.ventas_anio),
    conteo('puntos_venta', 'Puntos de venta',
      'Sucursales principales activas; los puntos asociados se cuentan dentro de su principal.',
      datos?.puntos_venta),
    asesores(datos?.asesores),
  ];
}
