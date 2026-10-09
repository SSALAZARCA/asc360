'use client';
/** "Inventario por tienda": one row per store; clicking a store narrows the whole KPI's view to it. */
import { miles, pct } from '../format';
import { COLOR } from '../tokens';
import { NUM, TARJETA, TITULO } from '../ventas/estilos';
import { pesosM, rotacionTexto } from './datos';
import { SUBTITULO, TARJETA_COLUMNA } from './estilos';
import { ChipDias } from './InventarioPorLinea';

const TH = { padding: '8px 6px' };
const TD = { ...NUM, padding: '9px 6px' };

function columnas(umbral) {
  return [
    { texto: 'Valor' },
    { texto: 'Días', tip: 'Inventario a costo ÷ costo de ventas diario de los últimos 3 meses' },
    { texto: 'Rotación', tip: 'Veces que el inventario se vende en un año' },
    { texto: `Sin mov. +${umbral} d`, tip: `Valor con más de ${umbral} días sin venta` },
    { texto: 'Disponib.', tip: 'Referencias vendidas en los últimos 3 meses que hoy tienen existencia' },
    { texto: 'Agotadas', tip: 'Referencias con venta reciente y existencia en cero' },
  ];
}

function FilaTienda({ t, cortes, onChange }) {
  return (
    <tr data-testid="fila-tienda" style={{ borderTop: '1px solid #F0F0EE', textAlign: 'right' }}>
      <th scope="row" style={{ ...TH, padding: '9px 6px', textAlign: 'left', fontWeight: 700 }}>
        <button type="button" className="inv-link" title="Filtrar la pestaña a esta tienda" onClick={() => onChange({ sucursales: [t.sucursal_id] })}>
          {t.nombre}
        </button>
      </th>
      <td style={TD}>{pesosM(t.valor)}</td>
      <td style={{ padding: '9px 6px' }}><ChipDias dias={t.dias} cortes={cortes} /></td>
      <td style={TD}>{rotacionTexto(t.rotacion)}</td>
      <td style={TD}>{pesosM(t.sin_movimiento_valor)}</td>
      <td style={TD}>{pct(t.disponibilidad_pct, 1)}</td>
      <td style={TD}>{miles(t.agotadas)}</td>
    </tr>
  );
}

export default function InventarioPorTienda({ data, onChange }) {
  return (
    <section aria-label="Inventario por tienda" style={{ ...TARJETA, ...TARJETA_COLUMNA }}>
      <div>
        <h2 style={TITULO}>Inventario por tienda</h2>
        <p style={SUBTITULO}>Ordenado por días de inventario, la más cargada primero · clic en una tienda para filtrar la pestaña</p>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', minWidth: 820, borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: 'right', fontSize: 11, fontWeight: 700, letterSpacing: '.04em', textTransform: 'uppercase', color: COLOR.muted }}>
              <th scope="col" style={{ ...TH, textAlign: 'left' }}>Tienda</th>
              {columnas(data.sin_movimiento_umbral_dias).map((c) => <th key={c.texto} scope="col" style={TH} title={c.tip}>{c.texto}</th>)}
            </tr>
          </thead>
          <tbody>
            {data.tiendas.map((t) => <FilaTienda key={t.sucursal_id} t={t} cortes={data.cortes_color} onChange={onChange} />)}
          </tbody>
        </table>
      </div>
    </section>
  );
}
