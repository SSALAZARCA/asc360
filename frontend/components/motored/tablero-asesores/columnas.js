/**
 * Column definitions of the "Tablero de asesores" table: eight groups under
 * a shared header. `tip` is the plain-Spanish formula shown as a tooltip
 * (project convention: any column whose meaning is not obvious explains itself).
 * Values arrive from the backend already computed; fractions are shown as %.
 */
import { decimal, entero, pesos, porcentaje } from './formato';
import { etiquetaMes } from './rango';

export const LINEAS = ['REPUESTOS', 'ACCESORIOS', 'LLANTAS', 'LUBRICANTES', 'BATERIAS', 'GPS', 'CASCOS'];
const nombreLinea = (linea) => linea.charAt(0) + linea.slice(1).toLowerCase();

const col = (id, label, render, tip) => ({ id, label, render, tip });
const porLinea = (prefijo, tipo, leer, formato) => LINEAS.map((linea) => col(
  `${prefijo}-${linea}`, `${prefijo === 'venta' ? '' : '% '}${nombreLinea(linea)}`.trim(),
  (f) => formato(leer(f)?.[linea]), tipo(nombreLinea(linea)),
));

export function construirGrupos(meses) {
  return [
    {
      id: 'venta', label: 'Venta', columnas: [
        col('venta-total', 'Venta total', (f) => pesos(f.venta.total),
          'Valor bruto menos descuentos de las líneas con línea comercial reconocida.'),
        col('venta-hmcl', 'Venta HMCL', (f) => pesos(f.venta.hmcl),
          'Venta a clientes HMCL (NIT 900723988 y 900883086).'),
        col('venta-sin-hmcl', 'Venta sin HMCL', (f) => pesos(f.venta.sin_hmcl), 'Venta total menos la venta HMCL.'),
        col('pct-hmcl', '% HMCL', (f) => porcentaje(f.venta.pct_hmcl), 'Venta HMCL dividida por la venta total.'),
        ...meses.map((mes) => col(`mes-${mes}`, etiquetaMes(mes), (f) => pesos(f.venta.por_mes?.[mes]),
          `Venta del mes ${etiquetaMes(mes)}.`)),
        ...porLinea('venta', (nombre) => `Venta de la línea ${nombre}.`, (f) => f.venta.por_linea, pesos),
      ],
    },
    {
      id: 'mix', label: 'Mix', columnas: porLinea(
        'mix', (nombre) => `Venta de ${nombre} dividida por la venta total de la fila.`, (f) => f.venta.mix, porcentaje),
    },
    {
      id: 'costo', label: 'Costo', columnas: [
        col('costo-venta', 'Costo de venta', (f) => pesos(f.costo.costo_venta),
          'Cantidad vendida por el costo unitario (mediana de los costos positivos del último inventario). Solo líneas que tienen costo.'),
        col('venta-con-costo', 'Venta con costo', (f) => pesos(f.costo.venta_con_costo),
          'Venta de las líneas cuya referencia tiene costo en el inventario.'),
        col('utilidad', 'Utilidad bruta', (f) => pesos(f.costo.utilidad_bruta), 'Venta con costo menos costo de venta.'),
        col('margen', '% margen', (f) => porcentaje(f.costo.pct_margen), 'Utilidad bruta dividida por la venta con costo.'),
        col('pct-con-costo', '% venta con costo', (f) => porcentaje(f.costo.pct_venta_con_costo),
          'Venta con costo dividida por la venta total. Si es baja, el margen no es confiable.'),
      ],
    },
    {
      id: 'tendencia', label: 'Tendencia', columnas: [
        col('t-ultimos', 'Últimos 3 meses', (f) => pesos(f.tendencia.ultimos_3m),
          'Venta de los últimos 3 meses del rango. Solo aparece si el rango tiene al menos 6 meses.'),
        col('t-previos', '3 meses previos', (f) => pesos(f.tendencia.previos_3m), 'Venta de los 3 meses anteriores a esos últimos 3.'),
        col('t-diferencia', 'Diferencia', (f) => pesos(f.tendencia.diferencia), 'Últimos 3 meses menos los 3 meses previos.'),
        col('t-pct', 'Var. %', (f) => porcentaje(f.tendencia.pct),
          'Venta de los últimos 3 meses dividida por la de los 3 previos, menos 1. Solo con rangos de 6 meses o más.'),
      ],
    },
    {
      id: 'facturas', label: 'Facturas', columnas: [
        col('f-total', 'Facturas', (f) => entero(f.facturas.facturas),
          'Facturas distintas (número de documento más sucursal) que tienen líneas de esta fila.'),
        col('f-ticket', 'Ticket promedio', (f) => pesos(f.facturas.ticket_promedio), 'Venta total dividida por el número de facturas.'),
        col('f-unidades', 'Unidades', (f) => entero(f.facturas.unidades), 'Suma de las cantidades vendidas.'),
        col('f-items', 'Ítems por factura', (f) => decimal(f.facturas.items_por_factura),
          'Líneas vendidas divididas por el número de facturas.'),
        ...porLinea('facturas', (nombre) => `Facturas con al menos una línea de ${nombre}, sobre el total de facturas.`,
          (f) => f.facturas.pct_con_linea, porcentaje),
        col('f-multilinea', '% multilínea', (f) => porcentaje(f.facturas.pct_multilinea),
          'Facturas con productos de más de una línea comercial, sobre el total de facturas.'),
      ],
    },
    {
      id: 'descuentos', label: 'Descuentos', columnas: [
        col('d-total', 'Descuentos', (f) => pesos(f.descuentos.total), 'Suma de los descuentos de las ventas.'),
        col('d-mes', 'Mes con más descuento', (f) => etiquetaMes(f.descuentos.mes_mayor), 'Mes en que se dio el mayor valor de descuentos.'),
        col('d-pct-mes', '% en ese mes', (f) => porcentaje(f.descuentos.pct_en_mes_mayor),
          'Parte del descuento total que cayó en ese mes.'),
        col('d-pct', '% descuento', (f) => porcentaje(f.descuentos.pct_descuento), 'Descuentos divididos por el valor bruto de las ventas.'),
      ],
    },
    {
      id: 'clientes', label: 'Clientes', columnas: [
        col('c-mostrador', '% mostrador', (f) => porcentaje(f.clientes.pct_mostrador), 'Venta hecha en mostrador dividida por la venta total.'),
        col('c-tecnired', 'Venta Tecnired', (f) => pesos(f.clientes.venta_tecnired), 'Venta a clientes de la lista Tecnired.'),
        col('c-pct-tecnired', '% Tecnired', (f) => porcentaje(f.clientes.pct_tecnired), 'Venta Tecnired dividida por la venta total.'),
        col('c-unicos', 'Clientes únicos', (f) => entero(f.clientes.clientes_unicos), 'Número de clientes distintos (por NIT o nombre normalizado).'),
        col('c-top5', '% top 5 clientes', (f) => porcentaje(f.clientes.pct_top5),
          'Venta de los 5 clientes que más compraron dividida por la venta total. Alto significa ventas concentradas.'),
      ],
    },
    {
      id: 'ranking', label: 'Ranking', columnas: [
        col('r-indice', 'Índice vs promedio', (f) => decimal(f.ranking?.indice_vs_promedio),
          'Venta total de la persona dividida por el promedio de todas las personas. 1,00 es el promedio. Solo entre personas, no entre grupos.'),
        col('r-total', 'Pos. total', (f) => entero(f.ranking?.rank_total), 'Posición por venta total (1 es la mayor) entre las personas.'),
        col('r-repuestos', 'Pos. repuestos', (f) => entero(f.ranking?.rank_repuestos), 'Posición por venta de repuestos entre las personas.'),
        col('r-accesorios', 'Pos. accesorios', (f) => entero(f.ranking?.rank_accesorios), 'Posición por venta de accesorios entre las personas.'),
        col('r-lubricantes', 'Pos. lubricantes', (f) => entero(f.ranking?.rank_lubricantes), 'Posición por venta de lubricantes entre las personas.'),
      ],
    },
  ];
}
