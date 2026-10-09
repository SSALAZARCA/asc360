/**
 * Dedicated editors by KEY (the generic control of a type still serves every
 * other key). `Control` edits the same draft the generic control edits;
 * `validar(borrador)` returns the Spanish messages that block saving.
 */
import EditorBonosLinea from './EditorBonosLinea';
import EditorLista, { itemsDe } from './EditorLista';
import EditorMapaCargos from './EditorMapaCargos';
import EditorSemaforo from './EditorSemaforo';
import EditorTiposExcluidos from './EditorTiposExcluidos';
import EditorTramos from './EditorTramos';
import {
  validarBonosLinea, validarLista, validarSemaforo, validarTiposExcluidos, validarTramos,
} from './validaciones';

const deLista = (opciones) => ({
  Control: (props) => <EditorLista {...props} {...opciones} />,
  validar: (borrador) => validarLista(itemsDe(borrador), opciones),
});

export const EDITORES = {
  hmcl_nits: deLista({ digitos: true, unicos: true }),
  lineas_comerciales: deLista({ mayusculas: true }),
  tipos_inventario_incluidos: deLista({ mayusculas: true }),
  estados_backorder_vigentes: deLista({ mayusculas: true }),
  bodegas_excluidas: deLista({ mayusculas: true, unicos: true }),
  comision_cargos_asesor: deLista({ mayusculas: true }),
  ingreso_tipos_pedido_excluidos: deLista({ mayusculas: true, unicos: true }),
  grupo_por_cargo: { Control: EditorMapaCargos },
  kpi_semaforo_cortes: { Control: EditorSemaforo, validar: validarSemaforo },
  comision_tramos: { Control: EditorTramos, validar: validarTramos },
  ventas_tipos_excluidos: { Control: EditorTiposExcluidos, validar: validarTiposExcluidos },
  comision_lineas: { Control: EditorBonosLinea, validar: (borrador) => validarBonosLinea(borrador) },
};

export const editorDe = (spec) => EDITORES[spec.clave] || null;
