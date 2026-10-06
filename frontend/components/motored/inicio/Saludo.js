/** Inicio: the greeting band (date, greeting with the first name, role chip). */
import { BAJADA, ROL_NOMBRE, fechaLarga, iniciales, momentoDelDia, primerNombre } from './textos';

const banda = {
  position: 'relative', overflow: 'hidden', display: 'flex', flexWrap: 'wrap', alignItems: 'center',
  justifyContent: 'space-between', gap: '24px', padding: 'clamp(20px, 3vw, 32px) clamp(20px, 3vw, 36px)',
  background: 'var(--motored-surface, #ffffff)', border: '1px solid var(--motored-border, #e4e4e7)',
  borderRadius: '12px',
};
const acento = {
  position: 'absolute', left: 0, top: 0, bottom: 0, width: '6px', background: 'var(--motored-brand, #e20714)',
};
const titulo = {
  margin: 0, fontFamily: 'var(--motored-font-kpi)', fontSize: 'clamp(26px, 3.2vw, 40px)', fontWeight: 800,
  letterSpacing: '-0.8px', lineHeight: 1.1, color: 'var(--motored-text, #1a1a18)',
};
const muted = 'var(--motored-text-muted, #5a5a5a)';
const persona = {
  display: 'flex', alignItems: 'center', gap: '12px', padding: '10px 16px 10px 10px', minWidth: 0,
  border: '1px solid var(--motored-border, #e4e4e7)', borderRadius: '999px',
  background: 'var(--motored-surface-alt, #f4f4f5)',
};
const avatar = {
  width: '40px', height: '40px', flexShrink: 0, borderRadius: '999px', display: 'flex', alignItems: 'center',
  justifyContent: 'center', background: 'var(--motored-brand-dark, #b00510)', color: '#ffffff',
  fontFamily: 'var(--motored-font-kpi)', fontWeight: 800, fontSize: '15px',
};

export default function Saludo({ usuario, ahora }) {
  const nombre = primerNombre(usuario?.nombre);
  const momento = momentoDelDia(ahora);
  return (
    <section aria-labelledby="inicio-saludo" style={banda}>
      <div style={acento} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', minWidth: 0 }}>
        <div style={{ fontSize: '13px', fontWeight: 700, color: muted, letterSpacing: '0.4px' }}>
          {fechaLarga(ahora)}
        </div>
        <h1 id="inicio-saludo" style={titulo}>{nombre ? `${momento}, ${nombre}` : momento}</h1>
        <p style={{ margin: 0, fontSize: '16px', color: muted, maxWidth: '56ch' }}>{BAJADA[usuario?.role] || ''}</p>
      </div>
      <div style={persona}>
        <div style={avatar} aria-hidden="true">{iniciales(usuario?.nombre)}</div>
        <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <span style={{ fontWeight: 700, fontSize: '14px' }}>{usuario?.nombre?.trim() || 'Usuario'}</span>
          <span style={{ fontSize: '12px', color: muted }}>{ROL_NOMBRE[usuario?.role] || ''}</span>
        </div>
      </div>
    </section>
  );
}
