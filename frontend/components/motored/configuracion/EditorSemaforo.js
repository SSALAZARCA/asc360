'use client';
/**
 * Semáforo cut points: two numbers (0 to 200) and a live preview of the
 * three bands, written in words so colour is never the only signal.
 */
import { controlStyle, filaStyle, mutedStyle } from './styles';
import Mensajes from './Mensajes';
import { validarSemaforo } from './validaciones';
import { numeroTexto } from './valor';

const CAMPOS = [
  { campo: 'verde_desde', etiqueta: 'Verde desde (%)' },
  { campo: 'ambar_desde', etiqueta: 'Ámbar desde (%)' },
];
const BANDAS = [
  { color: '#2e8b57', texto: ({ verde }) => `Verde: ${verde} % o más` },
  { color: '#d4a017', texto: ({ verde, ambar }) => `Ámbar: de ${ambar} % a menos de ${verde} %` },
  { color: '#c0392b', texto: ({ ambar }) => `Rojo: menos de ${ambar} %` },
];

function Vista({ borrador }) {
  const cortes = { verde: numeroTexto(borrador.verde_desde), ambar: numeroTexto(borrador.ambar_desde) };
  if (validarSemaforo(borrador).length) {
    return <p style={mutedStyle}>Corrija los valores para ver cómo queda el semáforo.</p>;
  }
  return (
    <ul style={{ ...filaStyle, listStyle: 'none', margin: 0, padding: 0 }} aria-label="Vista previa del semáforo">
      {BANDAS.map((b) => (
        <li key={b.color} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem' }}>
          <span aria-hidden="true" style={{ width: '14px', height: '14px', borderRadius: '50%', background: b.color }} />
          {b.texto(cortes)}
        </li>
      ))}
    </ul>
  );
}

export default function EditorSemaforo({ borrador, onChange }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <div style={filaStyle}>
        {CAMPOS.map(({ campo, etiqueta }) => (
          <label key={campo} style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', gap: '2px' }}>
            {etiqueta}
            <input
              type="text" inputMode="decimal" aria-label={etiqueta} value={borrador[campo]}
              style={{ ...controlStyle, width: '8rem' }} onChange={(e) => onChange({ ...borrador, [campo]: e.target.value })}
            />
          </label>
        ))}
      </div>
      <Vista borrador={borrador} />
      <Mensajes mensajes={validarSemaforo(borrador)} />
    </div>
  );
}
