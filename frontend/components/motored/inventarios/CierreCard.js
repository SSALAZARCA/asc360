/**
 * "Cierre" side card (WU12). EN_CONTEO: "Terminar primera vuelta" (close
 * stays disabled). EN_RECONTEO: the reconteos still open and "Cerrar
 * conteo". "Descargar avance en Excel" for every reader while open.
 */
import { cardStyle, mutedStyle } from './estilos';

const boton = { minHeight: '48px', fontWeight: 800 };

function resumen(conteo, items) {
  if (conteo.estado === 'EN_CONTEO') {
    return 'Primera vuelta en curso. Al terminarla se calculan las diferencias y se crean los reconteos.';
  }
  const abiertos = items.filter((f) => ['PENDIENTE', 'ASIGNADO'].includes(f.reconteo?.estado)).length;
  return abiertos ? `Faltan ${abiertos} reconteos por terminar.` : 'No quedan reconteos abiertos: el conteo se puede cerrar.';
}

export default function CierreCard({ conteo, items, opera, ocupado, onTerminarRonda, onCerrar, onDescargarAvance }) {
  const enConteo = conteo.estado === 'EN_CONTEO';
  return (
    <div style={cardStyle}>
      <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 800 }}>Cierre</h2>
      <div style={{ ...mutedStyle, fontSize: '0.8rem' }}>{resumen(conteo, items)}</div>
      {opera && enConteo && (
        <button type="button" className="motored-btn motored-btn-primary" style={boton} disabled={ocupado} onClick={onTerminarRonda}>
          Terminar primera vuelta
        </button>
      )}
      {opera && (
        <button
          type="button" className={`motored-btn ${enConteo ? 'motored-btn-secondary' : 'motored-btn-primary'}`} style={boton}
          disabled={enConteo || ocupado} onClick={onCerrar}
        >
          Cerrar conteo
        </button>
      )}
      <button type="button" className="motored-btn motored-btn-secondary" style={{ minHeight: '48px' }} disabled={ocupado} onClick={onDescargarAvance}>
        Descargar avance en Excel
      </button>
    </div>
  );
}
