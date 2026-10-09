'use client';
/** Body of one tab: the section's fields; Topes links to its own screen. */
import { useRouter } from 'next/navigation';
import SeccionAvisos from './SeccionAvisos';
import SeccionCargas from './SeccionCargas';
import SeccionComisiones from './SeccionComisiones';
import SeccionConteos from './SeccionConteos';
import SeccionIngresos from './SeccionIngresos';
import SeccionIndicadores from './SeccionIndicadores';
import SeccionLimpieza from './SeccionLimpieza';
import SeccionPedido from './SeccionPedido';
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

const PANELES = {
  pedido: SeccionPedido,
  avisos: SeccionAvisos,
  cargas: SeccionCargas,
  limpieza: SeccionLimpieza,
  indicadores: SeccionIndicadores,
  comisiones: SeccionComisiones,
  conteos: SeccionConteos,
  ingresos: SeccionIngresos,
};

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
      {seccion.id === 'topes' && <Topes />}
    </section>
  );
}
