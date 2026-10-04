'use client';
/** Pedido tab: the engine settings and the data-age limits, in five groups. */
import CamposDeSeccion from './CamposDeSeccion';
import ExcepcionesPorTienda from './ExcepcionesPorTienda';

const AVISO = 'Los cambios aplican a los pedidos nuevos; los ya calculados no cambian.';

const GRUPOS = [
  {
    titulo: 'Cobertura y frecuencia',
    campos: [
      {
        clave: 'dias_entre_pedidos', etiqueta: 'Días entre pedidos',
        ayuda: 'Cada cuántos días se hace un pedido a cada tienda. Con él se calcula cuánto hay que pedir para cubrir ese tiempo. Va de 1 a 60. Más abajo se puede fijar un valor propio para una tienda.',
      },
      {
        clave: 'modo_redondeo_empaque', etiqueta: 'Redondeo al empaque',
        ayuda: 'Qué hacer cuando la cantidad a pedir no es un múltiplo exacto del empaque: llevarla al múltiplo más cercano o siempre al siguiente múltiplo hacia arriba.',
      },
      {
        clave: 'modo_mes_en_curso', etiqueta: 'Mes en curso',
        ayuda: 'Qué hacer con las ventas del mes que todavía no termina: no contarlas, o contarlas con menos peso proyectando lo que falta del mes.',
      },
      {
        clave: 'tope_proyeccion_mes_actual', etiqueta: 'Tope de proyección del mes en curso',
        ayuda: 'Sólo si se cuenta el mes en curso: limita cuánto puede crecer la proyección de lo que falta del mes, medido en veces la mayor venta de los tres meses anteriores. 0 quita el límite.',
      },
      {
        clave: 'min_dias_mes_actual', etiqueta: 'Días mínimos del mes en curso',
        ayuda: 'Sólo si se cuenta el mes en curso: cuántos días del mes tienen que haber pasado para que se tenga en cuenta. Antes de eso el mes en curso no cuenta. Va de 1 a 28.',
      },
    ],
  },
  {
    titulo: 'Clasificación ABC/FMS',
    campos: [
      {
        clave: 'corte_abc_a', etiqueta: 'Corte de la clase A',
        ayuda: 'Hasta qué parte acumulada de la venta una referencia es clase A. 0,80 significa que las referencias que juntas suman el 80 % de la venta son A.',
      },
      {
        clave: 'corte_abc_b', etiqueta: 'Corte de la clase B',
        ayuda: 'Hasta qué parte acumulada de la venta una referencia es clase B; lo que pase de ahí es clase C. Debe ser mayor que el corte de la clase A.',
      },
      {
        clave: 'umbral_f', etiqueta: 'Umbral de frecuencia alta (F)',
        ayuda: 'En cuántos de los últimos 6 meses cerrados tiene que haber vendido una referencia para ser de frecuencia alta (F).',
      },
      {
        clave: 'umbral_m', etiqueta: 'Umbral de frecuencia media (M)',
        ayuda: 'En cuántos de los últimos 6 meses cerrados tiene que haber vendido una referencia para ser de frecuencia media (M). Las que venden menos son de baja frecuencia (S).',
      },
      {
        clave: 'k_fms', etiqueta: 'Seguridad por frecuencia (F, M, S)',
        ayuda: 'Cuántas veces se cuenta el tiempo de reposición (empaque, tránsito y seguridad) al calcular cuánto cubrir de cada referencia, según su frecuencia F, M o S. Un número mayor pide más.',
      },
    ],
  },
  {
    titulo: 'Mejoras opcionales',
    campos: [
      {
        clave: 'incluir_demanda_perdida_en_ponderada', etiqueta: 'Contar las ventas perdidas',
        ayuda: 'Suma lo que los clientes pidieron y no había (ventas perdidas) a la demanda con la que se calcula el pedido. Viene apagado.',
      },
      {
        clave: 'factor_demanda_perdida', etiqueta: 'Peso de las ventas perdidas',
        ayuda: 'Sólo si se cuentan las ventas perdidas: qué parte de cada venta perdida se suma. 1 es toda, 0,5 es la mitad.',
      },
      {
        clave: 'consolidar_sustituidas', etiqueta: 'Juntar referencias sustituidas',
        ayuda: 'Suma la demanda de una referencia a la de la que la sustituyó, para no pedir las dos. Viene apagado.',
      },
      {
        clave: 'excluir_transito_vencido', etiqueta: 'Ignorar tránsito vencido',
        ayuda: 'No cuenta como mercancía en camino la que ya pasó su plazo de llegada y no llegó. Viene apagado.',
      },
    ],
  },
  {
    titulo: 'Alertas',
    campos: [
      {
        clave: 'tolerancia_sobrestock', etiqueta: 'Margen de sobrestock',
        ayuda: 'Cuánto stock por encima del objetivo se tolera antes de marcar una referencia como sobrestock. 0,25 es un 25 %. Sólo cambia la marca, no las cantidades a pedir.',
      },
      {
        clave: 'meses_inventario_muerto', etiqueta: 'Meses para inventario muerto',
        ayuda: 'Cuántos meses sin venta hacen que una referencia con existencias se marque como inventario muerto. Va de 1 a 6. Sólo cambia la marca.',
      },
    ],
  },
  {
    titulo: 'Antigüedad de datos',
    campos: [
      {
        clave: 'max_dias_antiguedad_inventario', etiqueta: 'Antigüedad máxima del inventario (días)',
        ayuda: 'Cuántos días puede tener la última carga de inventario antes de que no se deje calcular un pedido. Va de 1 a 365. Antes de que se venza se avisa por Telegram (pestaña Avisos).',
      },
      {
        clave: 'max_dias_antiguedad_backorder', etiqueta: 'Antigüedad máxima del backorder (días)',
        ayuda: 'Cuántos días puede tener la última carga de backorder antes de que no se deje calcular un pedido. Va de 1 a 365.',
      },
      {
        clave: 'max_dias_antiguedad_facturas', etiqueta: 'Antigüedad máxima de las facturas de pedidos (días)',
        ayuda: 'Cuántos días pueden tener las últimas facturas de pedidos cargadas antes de que no se deje calcular un pedido. Va de 1 a 365.',
      },
      {
        clave: 'max_dias_antiguedad_ingresos', etiqueta: 'Antigüedad máxima de los ingresos (días)',
        ayuda: 'Cuántos días pueden tener los últimos ingresos de facturas cargados antes de que no se deje calcular un pedido. Va de 1 a 365.',
      },
    ],
  },
];

const DESPUES = {
  dias_entre_pedidos: (spec, props) => <ExcepcionesPorTienda spec={spec} {...props} />,
};

export default function SeccionPedido(props) {
  return <CamposDeSeccion {...props} aviso={AVISO} grupos={GRUPOS} despues={DESPUES} />;
}
