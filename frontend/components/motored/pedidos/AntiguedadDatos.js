/** Age of the datasets a corrida used (UX-06) plus the corrida warnings. */
import InfoTooltip from '../InfoTooltip';
import { dias, etiquetaDataset } from './formato';
import { mutedStyle } from './styles';

const AYUDA = 'Antigüedad de datos: días entre la fecha de corte y la última carga que usó el cálculo, contra el máximo permitido.';
const warnStyle = { color: 'var(--motored-warning, #d97706)', fontWeight: 700 };

function Dataset({ tipo, dato }) {
  const vencido = dato.antiguedad_dias > dato.limite_dias;
  return (
    <li style={vencido ? warnStyle : undefined}>
      {etiquetaDataset(tipo)}: {dato.antiguedad_dias == null ? 'sin datos' : dias(dato.antiguedad_dias)}
      {vencido && ` — supera el límite de ${dato.limite_dias}`}
    </li>
  );
}

export default function AntiguedadDatos({ antiguedad = {}, advertencias = [] }) {
  const tipos = Object.entries(antiguedad);
  if (tipos.length === 0 && advertencias.length === 0) return null;
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <h2 style={{ margin: 0, fontSize: '0.8rem', display: 'inline-flex', alignItems: 'center' }}>
        Antigüedad de datos<InfoTooltip text={AYUDA} />
      </h2>
      <ul style={{ ...mutedStyle, margin: 0, paddingLeft: '1.1rem' }}>
        {tipos.map(([tipo, dato]) => <Dataset key={tipo} tipo={tipo} dato={dato} />)}
      </ul>
      {advertencias.length > 0 && (
        <ul style={{ ...mutedStyle, margin: 0, paddingLeft: '1.1rem', color: 'var(--motored-warning, #d97706)' }}>
          {advertencias.map((a, i) => <li key={`${a.codigo}-${i}`}>{a.mensaje}</li>)}
        </ul>
      )}
    </section>
  );
}
