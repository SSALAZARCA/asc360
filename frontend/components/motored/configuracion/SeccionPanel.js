'use client';
/** Body of one tab. Empty placeholder until its task fills it; Topes links to its own screen. */
import { useRouter } from 'next/navigation';
import SeccionComisiones from './SeccionComisiones';
import SeccionIndicadores from './SeccionIndicadores';
import { cardStyle, columnaStyle, mutedStyle, touchStyle } from './styles';

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

const PANELES = { indicadores: SeccionIndicadores, comisiones: SeccionComisiones };

export default function SeccionPanel({ seccion, data = null, recargar, onGuardar }) {
  const Panel = PANELES[seccion.id];
  if (Panel) {
    return (
      <div style={columnaStyle} role="tabpanel" aria-label={seccion.label}>
        <Panel data={data} recargar={recargar} onGuardar={onGuardar} />
      </div>
    );
  }
  return (
    <section style={cardStyle} role="tabpanel" aria-label={seccion.label}>
      {seccion.id === 'topes'
        ? <Topes />
        : <p style={mutedStyle}>Esta sección se completa en una próxima entrega.</p>}
    </section>
  );
}
