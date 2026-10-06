/** Inicio: "Ir a", quick links to the sidebar screens of the role. */
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { grilla, seccion, tarjeta, textoSuave, tituloSeccion } from './estilos';

const icono = {
  width: '40px', height: '40px', borderRadius: '10px', display: 'flex', alignItems: 'center',
  justifyContent: 'center', background: 'var(--motored-brand-soft, #fde8ea)',
  color: 'var(--motored-brand-dark, #b00510)',
};

export default function IrA({ accesos }) {
  if (!accesos.length) return null;
  return (
    <section aria-labelledby="inicio-ir-a" style={seccion}>
      <h2 id="inicio-ir-a" style={tituloSeccion}>Ir a</h2>
      <div style={grilla(200)}>
        {accesos.map((a) => (
          <Link key={a.id} href={a.href} style={{ ...tarjeta, gap: '14px', padding: '20px' }}>
            <span style={icono} aria-hidden="true"><ArrowRight size={20} /></span>
            <span style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <span style={{ fontWeight: 800, fontSize: '15px' }}>{a.nombre}</span>
              {a.ayuda && <span style={textoSuave}>{a.ayuda}</span>}
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
