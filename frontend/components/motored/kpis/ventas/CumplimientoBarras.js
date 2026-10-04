import { barPlacement } from '../charts';
import { millones, pct } from '../format';
import { COLOR, TONO } from '../tokens';
import { NUM } from './estilos';

const COLUMNAS = 'minmax(130px, 200px) minmax(0, 1fr) 96px';
const ESCALA = 1.5;
const tonoDe = (f, zonas) => (f.fraccion === null ? 'none' : f.fraccion * 100 >= zonas.verde ? 'good' : f.fraccion * 100 >= zonas.ambar ? 'mid' : 'bad');

function Eje() {
  const marca = { position: 'absolute', transform: 'translateX(-50%)' };
  return (
    <div style={{ display: 'grid', gridTemplateColumns: COLUMNAS, gap: 12, fontSize: 11, color: COLOR.soft, position: 'sticky', top: 0, background: COLOR.surface, paddingBottom: 4, zIndex: 1 }}>
      <span />
      <div style={{ position: 'relative', height: 14 }}>
        <span style={{ position: 'absolute', left: 0 }}>0%</span>
        <span style={{ ...marca, left: `${(0.5 / ESCALA) * 100}%` }}>50%</span>
        <span data-testid="referencia-100" style={{ ...marca, left: `${(1 / ESCALA) * 100}%`, color: COLOR.ink, fontWeight: 700 }}>100%</span>
        <span style={{ position: 'absolute', right: 0 }}>150%</span>
      </div>
      <span />
    </div>
  );
}

function Valor({ texto, dentro }) {
  const estilo = dentro
    ? { color: '#FFFFFF', textShadow: '0 1px 1px rgba(0,0,0,.35)' }
    : { color: COLOR.ink2, position: 'absolute', left: 'calc(100% + 6px)' };
  return <span style={{ fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap', ...NUM, ...estilo }}>{texto}</span>;
}

function Fila({ fila, zonas }) {
  const color = TONO[tonoDe(fila, zonas)].color;
  const ancho = fila.fraccion === null ? 0 : Math.min((fila.fraccion / ESCALA) * 100, 100);
  return (
    <div data-testid="cumplimiento-fila" style={{ display: 'grid', gridTemplateColumns: COLUMNAS, gap: 12, alignItems: 'center' }}>
      <span data-testid="cumplimiento-nombre" style={{ fontSize: 12.5, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{fila.nombre}</span>
      <div style={{ position: 'relative', height: 20, background: COLOR.wash, borderRadius: 4 }}>
        {fila.fraccion !== null && (
          <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${ancho}%`, background: color, borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', paddingRight: 6, boxSizing: 'border-box' }}>
            <Valor texto={`${millones(fila.venta)} / ${millones(fila.presupuesto)}`} dentro={barPlacement(ancho) === 'inside'} />
          </div>
        )}
        <div style={{ position: 'absolute', top: -4, bottom: -4, left: `${(1 / ESCALA) * 100}%`, width: 2, background: COLOR.ink }} />
      </div>
      <span style={{ fontSize: fila.fraccion === null ? 11.5 : 13, fontWeight: 700, textAlign: 'right', color: fila.fraccion === null ? COLOR.muted : color, ...NUM }}>
        {fila.fraccion === null ? 'Sin presupuesto' : pct(fila.fraccion)}
      </span>
    </div>
  );
}

/** "Barras" view of the compliance per store: value inside the bar, % at the right, 100% reference line. */
export default function CumplimientoBarras({ filas, zonas }) {
  return (
    <div data-testid="cumplimiento-lista" style={{ display: 'flex', flexDirection: 'column', gap: 7, marginTop: 16, maxHeight: 340, overflowY: 'auto', paddingRight: 8 }}>
      <Eje />
      {filas.map((f) => <Fila key={f.id} fila={f} zonas={zonas} />)}
    </div>
  );
}
