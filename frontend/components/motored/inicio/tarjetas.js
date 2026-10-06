/**
 * Inicio: turns the endpoint's sections into "Para hoy" cards, the data
 * status tiles and the "Ir a" links. Pure functions, no React.
 */
import { menuItemsFor } from '../MotoredSidebar';
import { fechaBogota, horaBogota } from '../../../lib/motored/fechas';
import { formatCOP } from '../../../lib/motored/formatCOP';
import { AYUDA_ACCESO, AYUDA_MAESTROS_GERENCIA, NOMBRE_DATO } from './textos';

const NUMERO = new Intl.NumberFormat('es-CO');
const numero = (n) => NUMERO.format(Number(n) || 0);
const plural = (n, uno, varios) => `${numero(n)} ${Number(n) === 1 ? uno : varios}`;
const MESES = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre',
  'diciembre',
];

export const pestanaMaestros = (tipo) => `/motored/maestros?tab=${String(tipo).toLowerCase()}`;
const detalleCorrida = (s) => (s.corrida_id ? `/motored/pedidos/${s.corrida_id}` : '/motored/pedidos');

export const TITULOS = {
  pedidos_borrador: 'Pedidos en borrador',
  datos_por_vencer: 'Datos por vencer',
  detractores_sin_gestionar: 'Detractores sin gestionar',
  ultimo_pedido_enviado: 'Último pedido enviado',
  venta_mes: 'Venta del mes',
  tiendas_verde: 'Tiendas en verde',
  tiendas_rojo: 'Tiendas en rojo',
  encuestas_mes: 'Encuestas cargadas este mes',
};

function pedidosBorrador(s) {
  const valor = plural(s.tiendas, 'tienda', 'tiendas');
  if (!s.codigo) {
    return { valor, detalle: 'Todavía no hay pedidos calculados', chip: 'Al día', tono: 'ok', href: '/motored/pedidos' };
  }
  const pendientes = s.tiendas > 0;
  return {
    valor,
    detalle: pendientes
      ? `${s.codigo}: revisalos y cerralos antes de enviar a HMCL`
      : `${s.codigo}: no quedan tiendas en borrador`,
    chip: pendientes ? 'Revisar' : 'Al día',
    tono: pendientes ? 'ojo' : 'ok',
    href: detalleCorrida(s),
  };
}

const SEVERIDAD = ['vencido', 'sin_datos', 'por_vencer'];

function primeroPorAtender(datos = []) {
  for (const estado of SEVERIDAD) {
    const dato = datos.find((d) => d.estado === estado);
    if (dato) return dato;
  }
  return null;
}

function avisoDe(dato) {
  const nombre = NOMBRE_DATO[dato.tipo] || dato.tipo;
  if (dato.estado === 'vencido') return `${nombre} está vencido`;
  if (dato.estado === 'sin_datos') return `${nombre} no tiene cargas`;
  return `${nombre} vence ${dato.vence_cuando === 'hoy' ? 'hoy' : 'mañana'}`;
}

function datosPorVencer(s) {
  const primero = primeroPorAtender(s.datos);
  const graves = (s.vencidos || 0) + (s.sin_datos || 0);
  let chip = { chip: 'Al día', tono: 'ok' };
  if (graves > 0) chip = { chip: 'Atención', tono: 'mal' };
  else if (s.por_vencer > 0) chip = { chip: 'Revisar', tono: 'ojo' };
  return {
    valor: plural(s.cantidad, 'carga', 'cargas'),
    detalle: primero ? avisoDe(primero) : 'Todos los datos están al día',
    ...chip,
    href: pestanaMaestros(primero ? primero.tipo : 'INVENTARIO'),
  };
}

function detractores(s, rol) {
  const hay = s.cantidad > 0;
  return {
    valor: numero(s.cantidad),
    detalle: 'Clientes que calificaron mal el servicio',
    chip: hay ? 'Pendiente' : 'Al día',
    tono: hay ? (rol === 'SERVICIO_CLIENTE' ? 'mal' : 'neutro') : 'ok',
    href: '/motored/detractores',
  };
}

function ultimoEnviado(s) {
  if (!s.codigo) {
    return {
      valor: 'Ninguno', detalle: 'Todavía no se envió ningún pedido', chip: 'Pendiente', tono: 'neutro',
      href: '/motored/pedidos',
    };
  }
  const completo = s.enviadas >= s.total;
  return {
    valor: s.codigo,
    detalle: `${numero(s.enviadas)} de ${numero(s.total)} tiendas enviadas`,
    chip: completo ? 'Al día' : 'En curso',
    tono: completo ? 'ok' : 'neutro',
    href: detalleCorrida(s),
  };
}

function ventaMes(s) {
  if (s.estado === 'sin_presupuesto') {
    return {
      valor: formatCOP(s.venta), detalle: 'Cargá los presupuestos del mes', chip: 'Sin presupuesto', tono: 'ojo',
      href: pestanaMaestros('presupuestos'),
    };
  }
  return {
    valor: formatCOP(s.venta),
    detalle: `${numero(Math.round((s.pct || 0) * 100))}% del presupuesto a hoy`,
    nota: s.datos_actualizados_en ? `Datos de ventas al ${horaBogota(s.datos_actualizados_en)}` : null,
    chip: 'En curso',
    tono: 'neutro',
    href: '/motored/tablero-asesores',
  };
}

const tiendasVerde = (s) => ({
  valor: `${numero(s.cantidad)} de ${numero(s.total)}`,
  detalle: `Cumplimiento igual o mayor al ${numero(s.desde_pct)}%`,
  chip: 'Bien',
  tono: 'ok',
  href: '/motored/tablero-asesores',
});

const tiendasRojo = (s) => ({
  valor: numero(s.cantidad),
  detalle: `Cumplimiento menor al ${numero(s.menor_a_pct)}%`,
  chip: s.cantidad > 0 ? 'Atención' : 'Bien',
  tono: s.cantidad > 0 ? 'mal' : 'ok',
  href: '/motored/tablero-asesores',
});

const encuestasMes = (s) => ({
  valor: numero(s.registros),
  detalle: s.ultima_carga ? `Última carga: ${fechaBogota(s.ultima_carga)}` : 'Todavía no hay cargas',
  chip: s.cargas > 0 ? 'Al día' : 'Pendiente',
  tono: s.cargas > 0 ? 'ok' : 'ojo',
  href: '/motored/encuesta-satisfaccion',
});

const CONSTRUCTORES = {
  pedidos_borrador: pedidosBorrador,
  datos_por_vencer: datosPorVencer,
  detractores_sin_gestionar: detractores,
  ultimo_pedido_enviado: ultimoEnviado,
  venta_mes: ventaMes,
  tiendas_verde: tiendasVerde,
  tiendas_rojo: tiendasRojo,
  encuestas_mes: encuestasMes,
};

/** One card per known section, in the endpoint's order. */
export function tarjetasDe(secciones = {}, rol) {
  return Object.entries(secciones)
    .filter(([nombre]) => CONSTRUCTORES[nombre])
    .map(([nombre, seccion]) => {
      const base = { id: nombre, titulo: TITULOS[nombre] };
      if (!seccion?.disponible) return { ...base, noDisponible: true };
      return { ...base, ...CONSTRUCTORES[nombre](seccion, rol) };
    });
}

const ESTADO_DATO = {
  al_dia: { chip: 'Al día', tono: 'ok' },
  vencido: { chip: 'Vencida', tono: 'mal' },
  sin_datos: { chip: 'Sin datos', tono: 'mal' },
};

function fechaDato(dato) {
  if (!dato.fecha) return 'Sin cargas aplicadas';
  if (dato.tipo === 'VENTAS') {
    const [anio, mes] = dato.fecha.split('-');
    return `Hasta ${MESES[Number(mes) - 1]} ${anio}`;
  }
  const prefijo = ['INVENTARIO', 'BACKORDER'].includes(dato.tipo) ? 'Corte' : 'Aplicada';
  return `${prefijo} ${fechaBogota(dato.fecha)}`;
}

/** "Estado de los datos": one tile per data type. */
export function tilesDeDatos(datos = []) {
  return datos.map((dato) => {
    const estado = dato.estado === 'por_vencer'
      ? { chip: dato.vence_cuando === 'hoy' ? 'Vence hoy' : 'Vence mañana', tono: 'ojo' }
      : ESTADO_DATO[dato.estado] || ESTADO_DATO.sin_datos;
    return {
      id: dato.tipo,
      nombre: NOMBRE_DATO[dato.tipo] || dato.tipo,
      fecha: fechaDato(dato),
      href: pestanaMaestros(dato.tipo),
      ...estado,
    };
  });
}

/** "Ir a": the sidebar entries of the user (same role filter), minus Inicio itself and the account page. */
export function accesosDe(usuario) {
  return menuItemsFor(usuario)
    .flatMap((item) => item.children || [item])
    .filter((item) => item.id !== 'inicio' && item.id !== 'mi-cuenta')
    .map((item) => ({
      id: item.id,
      nombre: item.name,
      href: item.path,
      ayuda: item.id === 'maestros' && usuario?.role === 'GERENCIA'
        ? AYUDA_MAESTROS_GERENCIA
        : AYUDA_ACCESO[item.id] || '',
    }));
}
