'use client';
/** One parameter the user picked to test: what it means, the value in force and the control typed after the key. */
import InfoTooltip from '../InfoTooltip';
import { etiquetaClave, textoValor } from './escenario';
import { LEYENDO, NO_LEIDO, POR_DEFECTO } from './useEscenario';
import { cardStyle, errorStyle, mutedStyle, optionStyle } from './styles';

const campoStyle = { minHeight: '44px', boxSizing: 'border-box' };
const FACTORES = ['F', 'M', 'S'];

const NOTAS = {
  [POR_DEFECTO]: 'Este parámetro no tiene una versión propia: se muestra el valor por defecto.',
  [NO_LEIDO]: 'No se pudo leer el valor actual; se muestra el valor por defecto.',
};

function Control({ fila, nombre, onCambiar }) {
  const { tipo, borrador } = fila;
  const aria = `${nombre}: valor a probar`;
  if (tipo === 'bool') {
    return (
      <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', minHeight: '44px', fontSize: '0.85rem' }}>
        <input type="checkbox" aria-label={aria} checked={borrador} onChange={(e) => onCambiar(e.target.checked)} />
        Activado
      </label>
    );
  }
  if (tipo === 'opcion') {
    return (
      <select aria-label={aria} value={borrador} style={campoStyle} onChange={(e) => onCambiar(e.target.value)}>
        {fila.opciones.map((o) => <option key={o} value={o} style={optionStyle}>{o}</option>)}
      </select>
    );
  }
  if (tipo === 'k_fms') {
    return (
      <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
        {FACTORES.map((f) => (
          <label key={f} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.8rem' }}>
            {f}
            <input
              aria-label={`${nombre}: factor ${f}`} inputMode="decimal" value={borrador[f]}
              style={{ ...campoStyle, width: '5rem' }} onChange={(e) => onCambiar({ ...borrador, [f]: e.target.value })}
            />
          </label>
        ))}
      </div>
    );
  }
  return (
    <input aria-label={aria} inputMode="decimal" value={borrador} style={{ ...campoStyle, width: '8rem' }} onChange={(e) => onCambiar(e.target.value)} />
  );
}

export default function FilaPrueba({ fila, error, onCambiar, onQuitar }) {
  const { titulo, ayuda } = etiquetaClave(fila.clave);
  return (
    <div role="group" aria-label={titulo} style={{ ...cardStyle, padding: '0.75rem 1rem', gap: '0.4rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', justifyContent: 'space-between' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', fontSize: '0.85rem', fontWeight: 700 }}>
          {titulo}
          {ayuda && <InfoTooltip text={ayuda} />}
        </span>
        <button type="button" className="motored-btn motored-btn-secondary" style={{ minHeight: '44px' }} onClick={() => onQuitar(fila.clave)}>
          Quitar
        </button>
      </div>
      {fila.fuente === LEYENDO ? (
        <p style={mutedStyle}>Leyendo el valor actual...</p>
      ) : (
        <>
          <span style={mutedStyle}>{`Valor actual: ${textoValor(fila.tipo, fila.actual)}`}</span>
          {NOTAS[fila.fuente] && <span style={mutedStyle}>{NOTAS[fila.fuente]}</span>}
          <Control fila={fila} nombre={titulo} onCambiar={(borrador) => onCambiar(fila.clave, borrador)} />
          {error && <p aria-live="polite" style={{ ...errorStyle, margin: 0 }}>{error}</p>}
        </>
      )}
    </div>
  );
}
