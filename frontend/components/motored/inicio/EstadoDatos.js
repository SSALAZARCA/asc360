/** Inicio: "Estado de los datos" (ADMIN and COMPRAS), one tile per data the pedido needs. */
import Link from 'next/link';
import Chip from './Chip';
import InfoTooltip from '../InfoTooltip';
import { grilla, textoSuave, tituloSeccion } from './estilos';
import { NO_DISPONIBLE } from './textos';

const caja = {
  display: 'flex', flexDirection: 'column', gap: '16px', padding: 'clamp(16px, 2.5vw, 24px) clamp(16px, 2.5vw, 28px)',
  background: 'var(--motored-surface, #ffffff)', border: '1px solid var(--motored-border, #e4e4e7)',
  borderRadius: '12px',
};
const tile = {
  display: 'flex', flexDirection: 'column', gap: '6px', padding: '14px 16px', borderRadius: '10px',
  background: 'var(--motored-surface-alt, #f4f4f5)', color: 'var(--motored-text, #1a1a18)', textDecoration: 'none',
};
const AYUDA = 'Al día: sirve para el pedido. Vence hoy o mañana: conviene cargarlo ya. '
  + 'Vencida o sin datos: el pedido queda bloqueado hasta que se cargue.';

export default function EstadoDatos({ tiles, disponible }) {
  return (
    <section aria-labelledby="inicio-datos" style={caja}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', justifyContent: 'space-between', gap: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <h2 id="inicio-datos" style={tituloSeccion}>Estado de los datos</h2>
          <InfoTooltip text={AYUDA} />
        </div>
        <span style={textoSuave}>El pedido necesita que estén al día</span>
      </div>
      {disponible ? (
        <div style={{ ...grilla(190), gap: '12px' }}>
          {tiles.map((t) => (
            <Link key={t.id} href={t.href} style={tile}>
              <span data-nombre style={{ fontSize: '13px', fontWeight: 700 }}>{t.nombre}</span>
              <span style={{ ...textoSuave, fontSize: '12px' }}>{t.fecha}</span>
              <Chip tono={t.tono}>{t.chip}</Chip>
            </Link>
          ))}
        </div>
      ) : <span style={textoSuave}>{NO_DISPONIBLE}</span>}
    </section>
  );
}
