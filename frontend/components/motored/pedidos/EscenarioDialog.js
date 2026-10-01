'use client';
/**
 * "Nuevo escenario de prueba" (ADMIN): the same launch fields as a corrida plus
 * the engine parameters to test. The scenario never changes the real
 * parameters; it is a corrida marked PRUEBA to compare with the real one.
 */
import CamposCorrida from './CamposCorrida';
import DialogoPedido from './DialogoPedido';
import FilaPrueba from './FilaPrueba';
import useEscenario from './useEscenario';
import { etiquetaClave } from './escenario';
import { plural } from './formato';
import { errorStyle, labelStyle, mutedStyle, optionStyle } from './styles';

const DESCRIPCION = 'Pruebe qué pasaría si cambia uno o varios parámetros del cálculo. No modifica los parámetros reales: crea una corrida marcada como PRUEBA para compararla con la real. Un escenario no se cierra, no se exporta y no se envía.';

function Selector({ escenario: e }) {
  const { items, error } = e.catalogo;
  return (
    <>
      <label style={labelStyle}>
        Agregar un parámetro a probar
        <select
          value="" disabled={!items} style={{ minHeight: '44px', boxSizing: 'border-box' }}
          onChange={(ev) => ev.target.value && e.agregar(ev.target.value)}
        >
          <option value="" style={optionStyle}>{items ? 'Elija un parámetro...' : 'Cargando parámetros...'}</option>
          {e.disponibles.map((p) => <option key={p.clave} value={p.clave} style={optionStyle}>{etiquetaClave(p.clave).titulo}</option>)}
        </select>
      </label>
      {error && <p role="alert" style={errorStyle}>{error}</p>}
    </>
  );
}

function Resumen({ cambios }) {
  return (
    <p role="status" style={{ ...mutedStyle, margin: 0 }}>
      {cambios === 0 ? 'Cambie al menos un valor para lanzar el escenario.' : `${cambios} ${plural(cambios, 'cambio', 'cambios')} para probar`}
    </p>
  );
}

export default function EscenarioDialog({ onCerrar, onCreada }) {
  const e = useEscenario(onCreada);
  return (
    <DialogoPedido
      titulo="Nuevo escenario de prueba" descripcion={<p style={{ margin: 0 }}>{DESCRIPCION}</p>} ancho="680px"
      error={e.lanzar.error} ocupado={e.lanzar.busy} textoConfirmar="Lanzar escenario"
      confirmarDeshabilitado={!e.listo} onConfirm={e.lanzar.lanzar} onCancel={onCerrar}
    >
      <CamposCorrida lanzar={e.lanzar} />
      <Selector escenario={e} />
      {e.filas.map((fila) => (
        <FilaPrueba key={fila.clave} fila={fila} error={e.errores[fila.clave]} onCambiar={e.cambiar} onQuitar={e.quitar} />
      ))}
      <Resumen cambios={e.cambios} />
    </DialogoPedido>
  );
}
