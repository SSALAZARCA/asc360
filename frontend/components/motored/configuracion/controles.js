'use client';
/**
 * One control per registry type. Every control edits a DRAFT (see `valor.js`)
 * and reports the whole new draft through `onChange`. Controls are at least
 * 44 px tall and every <option> has an explicit colour (dark theme).
 */
import { Plus, Trash2 } from 'lucide-react';
import { columnaStyle, controlStyle, filaStyle, optionStyle, touchStyle } from './styles';

function Interruptor({ id, etiqueta, borrador, onChange }) {
  return (
    <input
      id={id} type="checkbox" aria-label={etiqueta} checked={Boolean(borrador)}
      style={{ width: '44px', height: '44px' }} onChange={(e) => onChange(e.target.checked)}
    />
  );
}

function Numero({ id, etiqueta, borrador, onChange, modo }) {
  return (
    <input
      id={id} type="text" inputMode={modo} aria-label={etiqueta} value={borrador}
      style={{ ...controlStyle, maxWidth: '12rem' }} onChange={(e) => onChange(e.target.value)}
    />
  );
}

function Opciones({ opciones }) {
  return opciones.map((o) => <option key={o} value={o} style={optionStyle}>{o}</option>);
}

function Seleccion({ id, etiqueta, borrador, onChange, spec }) {
  return (
    <select id={id} aria-label={etiqueta} value={borrador} style={controlStyle} onChange={(e) => onChange(e.target.value)}>
      <Opciones opciones={spec.opciones} />
    </select>
  );
}

function Lista({ id, etiqueta, borrador, onChange }) {
  return (
    <textarea
      id={id} aria-label={etiqueta} value={borrador} rows={4}
      style={{ ...touchStyle, width: '100%', maxWidth: '24rem' }} onChange={(e) => onChange(e.target.value)}
    />
  );
}

function Objeto({ spec, borrador, onChange }) {
  return (
    <div style={filaStyle}>
      {spec.campos.map((campo) => (
        <label key={campo} style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', gap: '2px' }}>
          {campo}
          <input
            type="text" inputMode="decimal" aria-label={campo} value={borrador[campo]}
            style={{ ...controlStyle, width: '8rem' }}
            onChange={(e) => onChange({ ...borrador, [campo]: e.target.value })}
          />
        </label>
      ))}
    </div>
  );
}

function BotonFila({ icono: Icono, texto, onClick, conTexto = false }) {
  return (
    <button type="button" aria-label={texto} className="motored-btn motored-btn-secondary" style={touchStyle} onClick={onClick}>
      <Icono size={14} aria-hidden="true" />
      {conTexto ? ` ${texto}` : null}
    </button>
  );
}

function ListaDeFilas({ filas, onChange, vacia, children }) {
  const cambiar = (i, parche) => onChange(filas.map((f, j) => (j === i ? { ...f, ...parche } : f)));
  const quitar = (i) => onChange(filas.filter((_, j) => j !== i));
  return (
    <div style={columnaStyle}>
      {filas.map((fila, i) => (
        // eslint-disable-next-line react/no-array-index-key
        <div key={i} style={filaStyle}>
          {children(fila, (parche) => cambiar(i, parche))}
          <BotonFila icono={Trash2} texto="Quitar fila" onClick={() => quitar(i)} />
        </div>
      ))}
      <div><BotonFila icono={Plus} texto="Agregar fila" conTexto onClick={() => onChange([...filas, vacia])} /></div>
    </div>
  );
}

function Mapa({ spec, borrador, onChange }) {
  return (
    <ListaDeFilas filas={borrador} onChange={onChange} vacia={{ clave: '', valor: spec.opciones[0] }}>
      {(fila, cambiar) => (
        <>
          <input
            type="text" aria-label="Nombre de la fila" value={fila.clave}
            style={{ ...controlStyle, width: '16rem' }} onChange={(e) => cambiar({ clave: e.target.value })}
          />
          <select aria-label="Grupo de la fila" value={fila.valor} style={controlStyle} onChange={(e) => cambiar({ valor: e.target.value })}>
            <Opciones opciones={spec.opciones} />
          </select>
        </>
      )}
    </ListaDeFilas>
  );
}

function CeldaTramo({ etiqueta, valor, ancho, modo, onChange }) {
  return (
    <input
      type="text" inputMode={modo} aria-label={etiqueta} value={valor}
      style={{ ...controlStyle, width: ancho }} onChange={(e) => onChange(e.target.value)}
    />
  );
}

function Tramos({ borrador, onChange }) {
  const vacia = { nombre: '', desde_pct: '', tasa_pct: '' };
  return (
    <ListaDeFilas filas={borrador} onChange={onChange} vacia={vacia}>
      {(fila, cambiar) => (
        <>
          <CeldaTramo etiqueta="Nombre del tramo" valor={fila.nombre} ancho="10rem" onChange={(v) => cambiar({ nombre: v })} />
          <CeldaTramo etiqueta="Desde (%)" valor={fila.desde_pct} ancho="6rem" modo="decimal" onChange={(v) => cambiar({ desde_pct: v })} />
          <CeldaTramo etiqueta="Tasa (%)" valor={fila.tasa_pct} ancho="6rem" modo="decimal" onChange={(v) => cambiar({ tasa_pct: v })} />
        </>
      )}
    </ListaDeFilas>
  );
}

/** Types whose control is one field (the visible label points at it). */
export const TIPOS_SIMPLES = ['bool', 'entero', 'decimal', 'opcion', 'lista', 'lista_digitos'];

export default function ControlValor({ spec, etiqueta, id, borrador, onChange }) {
  const comun = { id, etiqueta, borrador, onChange, spec };
  switch (spec.tipo) {
    case 'bool': return <Interruptor {...comun} />;
    case 'entero': return <Numero {...comun} modo="numeric" />;
    case 'decimal': return <Numero {...comun} modo="decimal" />;
    case 'opcion': return <Seleccion {...comun} />;
    case 'lista':
    case 'lista_digitos': return <Lista {...comun} />;
    case 'k_fms':
    case 'objeto_numerico': return <Objeto {...comun} />;
    case 'mapa_opcion': return <Mapa {...comun} />;
    case 'tramos': return <Tramos {...comun} />;
    default: return <p>{`Tipo «${spec.tipo}» sin control.`}</p>;
  }
}
