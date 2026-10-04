/**
 * Dedicated editors by KEY (the generic control of a type still serves every
 * other key). `Control` edits the same draft the generic control edits;
 * `validar(borrador)` returns the Spanish messages that block saving.
 */
import EditorLista, { itemsDe } from './EditorLista';
import EditorMapaCargos from './EditorMapaCargos';
import EditorSemaforo from './EditorSemaforo';
import EditorTramos from './EditorTramos';
import { validarLista, validarSemaforo, validarTramos } from './validaciones';

const deLista = (opciones) => ({
  Control: (props) => <EditorLista {...props} {...opciones} />,
  validar: (borrador) => validarLista(itemsDe(borrador), opciones),
});

export const EDITORES = {
  hmcl_nits: deLista({ digitos: true, unicos: true }),
  lineas_comerciales: deLista({ mayusculas: true }),
  comision_cargos_asesor: deLista({ mayusculas: true }),
  grupo_por_cargo: { Control: EditorMapaCargos },
  kpi_semaforo_cortes: { Control: EditorSemaforo, validar: validarSemaforo },
  comision_tramos: { Control: EditorTramos, validar: validarTramos },
};

export const editorDe = (spec) => EDITORES[spec.clave] || null;
