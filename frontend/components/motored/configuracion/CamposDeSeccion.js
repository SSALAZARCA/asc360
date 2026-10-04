'use client';
/**
 * The fields of one tab: the notice(s) at the top and one CampoConfiguracion
 * per key the tab owns. `campos` gives each key its business wording; a key
 * the server did not return is skipped. `grupos` ([{ titulo, campos }])
 * splits the fields under headings; `despues` ({ clave: (spec, props) =>
 * node }) adds a block right under one field.
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

function Campos({ data, campos, despues, recargar, onGuardar }) {
  return campos.map(({ clave, etiqueta, ayuda }) => {
    const spec = especDe(data, clave);
    if (!spec) return null;
    return (
      <div key={clave} style={columnaStyle}>
        <CampoConfiguracion
          spec={spec} etiqueta={etiqueta} ayuda={ayuda} onGuardado={recargar}
          {...(onGuardar ? { onGuardar } : {})}
        />
        {despues[clave]?.(spec, { etiqueta, ayuda, recargar, onGuardar })}
      </div>
    );
  });
}

export default function CamposDeSeccion({
  data, aviso, campos, grupos, despues = {}, recargar, onGuardar,
}) {
  const bloques = grupos || [{ titulo: null, campos }];
  return (
    <>
      {[].concat(aviso).map((texto) => <p key={texto} style={mutedStyle}>{texto}</p>)}
      {bloques.map((bloque) => (
        <div key={bloque.titulo || 'campos'} style={columnaStyle}>
          {bloque.titulo && <h2 style={{ margin: 0, fontSize: '1rem' }}>{bloque.titulo}</h2>}
          <Campos data={data} campos={bloque.campos} despues={despues} recargar={recargar} onGuardar={onGuardar} />
        </div>
      ))}
    </>
  );
}
