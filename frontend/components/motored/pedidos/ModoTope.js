'use client';
/** The budget cap mode: a switch for the ADMIN, plain text for everyone else. */
import InfoTooltip from '../InfoTooltip';
import { fechaCorta } from './reglas';
import { cardStyle, errorStyle, mutedStyle } from './styles';

const MODO_TEXTO = 'Modo tope de presupuesto: cuando está activado, el pedido de una tienda que pasa de su tope muestra un aviso y una propuesta de recorte. Nunca recorta nada solo: el comprador decide si aplicarla.';

function estadoTexto(activo, desde) {
  if (!activo) return 'Desactivado';
  return desde ? `Activado desde ${fechaCorta(desde)}` : 'Activado';
}

export default function ModoTope({ activo, desde, editable, ocupado, error, onCambiar }) {
  const estado = estadoTexto(activo, desde);
  return (
    <section style={cardStyle}>
      {editable ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', minHeight: '44px', fontWeight: 600 }}>
            <input
              type="checkbox" checked={activo} disabled={ocupado} onChange={(e) => onCambiar(e.target.checked)}
              style={{ width: '20px', height: '20px' }}
            />
            Modo tope de presupuesto
          </label>
          <InfoTooltip text={MODO_TEXTO} />
          <span style={mutedStyle}>{estado}</span>
        </div>
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          <span style={{ fontWeight: 600 }}>{`Modo tope: ${estado}`}</span>
          <InfoTooltip text={MODO_TEXTO} />
          <span style={mutedStyle}>Solo el administrador puede cambiar el modo y los topes. Aquí los puede consultar.</span>
        </div>
      )}
      {error && <p role="alert" style={errorStyle}>{error}</p>}
    </section>
  );
}
