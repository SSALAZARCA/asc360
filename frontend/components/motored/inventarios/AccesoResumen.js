/** "Acceso para parejas" side card of the live panel (WU12): the code if just generated, else hidden; QR and rotate. */
import { formatCodigo } from './conteosFormato';
import { cardStyle, errorStyle, monoStyle, mutedStyle } from './estilos';

export default function AccesoResumen({ acceso, onVerAcceso }) {
  return (
    <div style={cardStyle}>
      <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 800 }}>Acceso para parejas</h2>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.6rem' }}>
        <span style={{ ...mutedStyle, fontSize: '0.8rem' }}>Código</span>
        {acceso.codigo ? (
          <span style={{ ...monoStyle, fontSize: '1.5rem', fontWeight: 600, letterSpacing: '0.08em' }}>{formatCodigo(acceso.codigo)}</span>
        ) : (
          <span style={mutedStyle}>Código oculto</span>
        )}
      </div>
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        <button type="button" className="motored-btn motored-btn-secondary" style={{ minHeight: '44px' }} onClick={onVerAcceso}>Ver QR y enlace</button>
        <button type="button" className="motored-btn motored-btn-secondary" style={{ minHeight: '44px' }} onClick={acceso.rotar}>Cambiar código</button>
      </div>
      {acceso.error && <p role="alert" style={errorStyle}>{acceso.error}</p>}
    </div>
  );
}
