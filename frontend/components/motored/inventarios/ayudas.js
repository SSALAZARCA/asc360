/** Tooltip texts of the inventory counts screens (convention: every non-obvious term gets one). */
export const AYUDA_EXACTITUD = 'Porcentaje de referencias cuyo conteo coincide con el sistema. Mientras se cuenta, se calcula solo sobre lo ya contado; al cerrar, sobre todo el inventario.';
export const AYUDA_AVANCE = 'Referencias de la foto del inventario (con existencia distinta de cero) que ya tienen al menos una lectura en la primera vuelta. Los reconteos no suman avance.';
export const AYUDA_RECONTEO = 'Segunda revisión de una referencia con diferencia, hecha siempre por otra pareja. Se crea sola desde el umbral de plata o la pide el líder.';
export const AYUDA_CRITICA = 'Diferencia cuyo valor al costo promedio pasa el umbral crítico de Configuración. Se muestra en rojo y arriba.';
export const AYUDA_FORZAR = 'Cierra aunque queden reconteos sin terminar: esos reconteos se cancelan y cuenta lo de la primera vuelta. Exige un motivo, que queda registrado.';
export const AYUDA_UNIDADES = 'Total de unidades contadas hasta ahora. Es la misma cantidad que muestra la columna "Contado" de la tabla de diferencias, sumada en todas las referencias.';
export const AYUDA_DENTRO = 'Unidades contadas que caben dentro de lo que el sistema dice que hay de cada referencia. Ejemplo: si el sistema tiene 10 y se cuentan 8, las 8 están dentro de lo esperado.';
export const AYUDA_SOBRANTES = 'Unidades contadas por encima de lo que el sistema tiene de cada referencia. Incluye las referencias que el sistema no tiene y los códigos desconocidos. Solo bajan si una pareja anula una lectura.';
