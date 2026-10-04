/** Business wording for options whose stored value is a code. */
export const ETIQUETA_OPCION = {
  sin_hmcl: 'Sin HMCL',
  con_hmcl: 'Con HMCL',
  CERCANO: 'Al múltiplo más cercano',
  ARRIBA: 'Siempre hacia arriba',
  EXCLUIDO: 'No contar el mes en curso',
  PONDERADO: 'Contarlo con menos peso',
  ADMIN: 'Administración',
  COMPRAS: 'Compras',
};

export const etiquetaDe = (codigo) => ETIQUETA_OPCION[codigo] || codigo;
