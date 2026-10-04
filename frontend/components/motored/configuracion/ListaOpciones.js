'use client';
/**
 * A list of values chosen from the spec's options, one checkbox each. The
 * draft is the array of chosen codes, always in the order of the options so
 * the saved value does not depend on the order of the clicks.
 */
import { etiquetaDe } from './etiquetas';
import { filaStyle } from './styles';

export default function ListaOpciones({ spec, borrador, onChange }) {
  const marcados = Array.isArray(borrador) ? borrador : [];
  const alternar = (opcion) => onChange(
    spec.opciones.filter((o) => (o === opcion ? !marcados.includes(o) : marcados.includes(o))),
  );
  return (
    <div style={{ ...filaStyle, gap: '1rem' }}>
      {spec.opciones.map((opcion) => (
        <label key={opcion} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minHeight: '44px' }}>
          <input
            type="checkbox" checked={marcados.includes(opcion)} style={{ width: '44px', height: '44px' }}
            onChange={() => alternar(opcion)}
          />
          {etiquetaDe(opcion)}
        </label>
      ))}
    </div>
  );
}
