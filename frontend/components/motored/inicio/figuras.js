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
const LINEA = 'Suma de ventas de la línea Repuestos';
const TODAS = 'todas las tiendas.';

const mayuscula = (texto) => texto.charAt(0).toUpperCase() + texto.slice(1);

/** "2026-09" -> "septiembre de 2026" / "Septiembre 2026"; null if unknown. */
function mesDe(aaaaMm) {
  const [anio, mes] = String(aaaaMm || '').split('-');
  const nombre = MESES[Number(mes) - 1];
  return nombre ? { largo: `${nombre} de ${anio}`, corto: `${mayuscula(nombre)} ${anio}` } : null;
}

const disponible = (figura) => Boolean(figura?.disponible);

function ventasMes(figura) {
  const mes = disponible(figura) ? mesDe(figura.mes) : null;
  return {
    id: 'ventas_mes',
    titulo: 'Ventas del último mes — Repuestos',
    subtitulo: mes?.corto ?? null,
    valor: mes ? formatCOP(figura.valor) : null,
    ayuda: mes ? `${LINEA} en ${mes.largo}, ${TODAS}` : `${LINEA} del último mes completo, ${TODAS}`,
  };
}

function ventasAnio(figura) {
  const ok = disponible(figura);
  const anio = ok ? String(figura.desde).slice(0, 4) : null;
  return {
    id: 'ventas_anio',
    titulo: 'Ventas acumuladas del año — Repuestos',
    subtitulo: 'Enero a hoy',
    valor: ok ? formatCOP(figura.valor) : null,
    ayuda: anio
      ? `${LINEA} desde el 1 de enero de ${anio} hasta hoy, ${TODAS}`
      : `${LINEA} desde el 1 de enero hasta hoy, ${TODAS}`,
  };
}

function conteo(id, titulo, ayuda, figura) {
  return {
    id, titulo, ayuda, subtitulo: null,
    valor: disponible(figura) ? ENTERO.format(figura.cantidad) : null,
  };
}

export function figurasDe(datos) {
  return [
    ventasMes(datos?.ventas_mes),
    ventasAnio(datos?.ventas_anio),
    conteo('puntos_venta', 'Puntos de venta',
      'Sucursales principales activas; los puntos asociados se cuentan dentro de su principal.',
      datos?.puntos_venta),
    conteo('asesores', 'Asesores', 'Asesores activos en el maestro de Vendedores.', datos?.asesores),
  ];
}
