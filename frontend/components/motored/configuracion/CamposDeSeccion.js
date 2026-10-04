'use client';
/**
 * The fields of one tab: the notice at the top and one CampoConfiguracion
 * per key the tab owns. `campos` gives each key its business wording; a key
 * the server did not return is skipped.
 */
import CampoConfiguracion from './CampoConfiguracion';
import { columnaStyle, mutedStyle } from './styles';

function especDe(data, clave) {
  const secciones = (data && data.secciones) || [];
  for (const seccion of secciones) {
    for (const grupo of seccion.grupos) {
      const encontrada = grupo.claves.find((c) => c.clave === clave);
      if (encontrada) return encontrada;
    }
  }
  return null;
}

export default function CamposDeSeccion({ data, aviso, campos, recargar, onGuardar }) {
  return (
    <>
      <p style={mutedStyle}>{aviso}</p>
      <div style={columnaStyle}>
        {campos.map(({ clave, etiqueta, ayuda }) => {
          const spec = especDe(data, clave);
          if (!spec) return null;
          return (
            <CampoConfiguracion
              key={clave} spec={spec} etiqueta={etiqueta} ayuda={ayuda} onGuardado={recargar}
              {...(onGuardar ? { onGuardar } : {})}
            />
          );
        })}
      </div>
    </>
  );
}
