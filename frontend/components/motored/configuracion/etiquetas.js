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
  PERSONA: 'Persona',
  COMERCIALES: 'Comerciales',
  OTROS: 'Otros',
};

export const etiquetaDe = (codigo) => ETIQUETA_OPCION[codigo] || codigo;

/** The lines of the per-line bonus (comision_lineas): stored code -> business name. */
export const ETIQUETA_LINEA = {
  REPUESTOS: 'Repuestos',
  ACCESORIOS: 'Otros accesorios',
  LLANTAS: 'Llantas',
  LUBRICANTES: 'Lubricantes',
  BATERIAS: 'Baterías',
  GPS: 'GPS',
  CASCOS: 'Cascos',
  TECNIRED: 'Tecnired (clientes)',
};

export const etiquetaLinea = (codigo) => ETIQUETA_LINEA[codigo] || codigo;
