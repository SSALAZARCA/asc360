'use client';
/** Body of one tab. Empty placeholder until its task fills it; Topes links to its own screen. */
import { useRouter } from 'next/navigation';
import { cardStyle, mutedStyle, touchStyle } from './styles';

export const RUTA_TOPES = '/motored/pedidos/topes';

function Topes() {
  const router = useRouter();
  return (
    <>
      <p style={mutedStyle}>El tope de presupuesto de cada tienda se edita en su propia pantalla.</p>
      <div>
        <button type="button" className="motored-btn motored-btn-primary" style={touchStyle} onClick={() => router.push(RUTA_TOPES)}>
          Ir a Topes por tienda
        </button>
      </div>
    </>
  );
}

export default function SeccionPanel({ seccion }) {
  return (
    <section style={cardStyle} role="tabpanel" aria-label={seccion.label}>
      {seccion.id === 'topes'
        ? <Topes />
        : <p style={mutedStyle}>Esta sección se completa en una próxima entrega.</p>}
    </section>
  );
}
