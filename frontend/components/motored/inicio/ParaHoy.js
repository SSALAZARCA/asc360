/** Inicio: "Para hoy", one card per section of the role (a link to its screen). */
import Link from 'next/link';
import Chip from './Chip';
import { grilla, seccion, tarjeta, textoSuave, tituloSeccion } from './estilos';
import { NO_DISPONIBLE } from './textos';

const valorStyle = {
  fontFamily: 'var(--motored-font-kpi)', fontSize: '30px', fontWeight: 800, letterSpacing: '-0.6px',
  overflowWrap: 'anywhere',
};
const tituloStyle = { fontSize: '13px', fontWeight: 700, color: 'var(--motored-text-muted, #5a5a5a)' };

function Cabecera({ titulo, chip, tono }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
      <span data-titulo style={tituloStyle}>{titulo}</span>
      {chip && <Chip tono={tono}>{chip}</Chip>}
    </div>
  );
}

function Tarjeta({ t }) {
  if (t.noDisponible) {
    return (
      <div style={{ ...tarjeta, minHeight: '132px', background: 'var(--motored-surface-alt, #f4f4f5)' }}>
        <Cabecera titulo={t.titulo} />
        <span style={textoSuave}>{NO_DISPONIBLE}</span>
      </div>
    );
  }
  return (
    <Link href={t.href} style={{ ...tarjeta, minHeight: '132px' }}>
      <Cabecera titulo={t.titulo} chip={t.chip} tono={t.tono} />
      <span style={valorStyle}>{t.valor}</span>
      <span style={textoSuave}>{t.detalle}</span>
      {t.nota && <span style={{ ...textoSuave, fontSize: '12px' }}>{t.nota}</span>}
    </Link>
  );
}

function Esqueleto() {
  const caja = { ...tarjeta, minHeight: '132px', background: 'var(--motored-surface-alt, #f4f4f5)' };
  return (
    <div data-testid="inicio-cargando" aria-busy="true" aria-label="Cargando" style={grilla(240)}>
      {[0, 1, 2].map((n) => <div key={n} style={caja} />)}
    </div>
  );
}

export default function ParaHoy({ tarjetas, cargando, error }) {
  let cuerpo;
  if (cargando) cuerpo = <Esqueleto />;
  else if (error) {
    cuerpo = (
      <p role="alert" style={{ margin: 0, color: 'var(--motored-danger, #c0392b)', fontWeight: 600 }}>
        No pudimos cargar tu resumen. Probá recargar la página en unos minutos.
      </p>
    );
  } else {
    cuerpo = (
      <div style={grilla(240)}>
        {tarjetas.map((t) => <Tarjeta key={t.id} t={t} />)}
      </div>
    );
  }
  return (
    <section aria-labelledby="inicio-para-hoy" style={seccion}>
      <h2 id="inicio-para-hoy" style={tituloSeccion}>Para hoy</h2>
      {cuerpo}
    </section>
  );
}
