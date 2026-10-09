/**
 * "Contado en <ubicación>": what THIS pair counted per code in the current
 * location. Never the system quantity (blind count). Tapping a row selects
 * it in the "Última lectura" card to correct it.
 */
import { C, MONO, tarjeta } from './estilos';
import { TEXTOS, formatoCantidad, textoReferencias } from './textos';

function Fila({ fila, resaltada, onSeleccionar }) {
  return (
    <li style={{ listStyle: 'none', borderBottom: '1px solid #f0f0f2', background: resaltada ? C.okFondo : 'transparent' }}>
      <button
        type="button"
        onClick={() => onSeleccionar(fila)}
        style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, padding: '12px 20px', background: 'transparent', border: 'none', textAlign: 'left', cursor: 'pointer', fontFamily: 'inherit', color: C.tinta }}
      >
        <span style={{ minWidth: 0 }}>
          <span style={{ display: 'block', fontFamily: MONO, fontWeight: 600, fontSize: 14, overflowWrap: 'anywhere' }}>{fila.codigo}</span>
          {fila.descripcion && <span style={{ display: 'block', fontSize: 12, color: C.medio }}>{fila.descripcion}</span>}
        </span>
        <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 600 }}>{formatoCantidad(fila.cantidad)}</span>
      </button>
    </li>
  );
}

export default function ListaContado({ ubicacion, filas, ultimaCodigo, onSeleccionar, style }) {
  const nombre = ubicacion ? (ubicacion.nombre || ubicacion.codigo) : '';
  const titulo = ubicacion ? `Contado en ${nombre}` : 'Contado';
  const ordenadas = [...filas].sort((a, b) => {
    if (a.codigo === ultimaCodigo) return -1;
    if (b.codigo === ultimaCodigo) return 1;
    return a.codigo.localeCompare(b.codigo);
  });
  return (
    <section style={{ ...tarjeta, display: 'flex', flexDirection: 'column', ...style }}>
      <div style={{ padding: '16px 20px', borderBottom: `1px solid ${C.borde}`, display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
        <h2 style={{ margin: 0, fontSize: 17, fontWeight: 800 }}>{titulo}</h2>
        <span style={{ fontSize: 13, color: C.medio }}>{textoReferencias(filas.length)}</span>
      </div>
      {ordenadas.length > 0 ? (
        <ul aria-label={titulo} style={{ margin: 0, padding: 0 }}>
          {ordenadas.map((f) => (
            <Fila key={f.codigo} fila={f} resaltada={f.codigo === ultimaCodigo} onSeleccionar={onSeleccionar} />
          ))}
        </ul>
      ) : (
        <div style={{ padding: '14px 20px', fontSize: 14, color: C.medio }}>
          {ubicacion ? 'Todavía no hay lecturas en esta ubicación.' : 'Indique la ubicación para empezar.'}
        </div>
      )}
      <div style={{ padding: '14px 20px', fontSize: 13, color: C.medio }}>{TEXTOS.notaCiega}</div>
    </section>
  );
}
