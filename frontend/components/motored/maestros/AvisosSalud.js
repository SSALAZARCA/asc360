'use client';
/**
 * Health warnings of the active Maestros tab: a collapsed summary that
 * expands into the affected codes grouped by reason, so the coloured dot
 * next to the tab label says WHAT to fix, not only that something is off.
 */
import { useState } from 'react';

const TITULOS = {
  referencia_sin_precio: 'Sin precio normal',
  unidad_empaque_corregida: 'Unidad de empaque corregida a 1',
  sucursal_sin_sic: 'Sin código SIC',
  bodega_sin_sucursal: 'Sin sucursal asociada',
};

const AYUDAS = {
  referencia_sin_precio: 'No suman valor en el pedido. Cargue el precio con la carga masiva de referencias.',
  unidad_empaque_corregida: 'Venían con empaque 0 o vacío. Revise el empaque real.',
  sucursal_sin_sic: 'Sin SIC no se puede identificar la tienda ante HMCL ni calcular su pedido.',
  bodega_sin_sucursal: 'Su inventario no se asigna a ninguna tienda.',
};

const CODIGO_ENTRE_COMILLAS = /'([^']+)'/;

const cajaStyle = (bloqueante) => ({
  border: `1px solid ${bloqueante ? 'var(--motored-danger, #c0392b)' : 'var(--motored-warning, #d97706)'}`,
  borderRadius: 'var(--motored-radius-md, 8px)',
  padding: '0.75rem 1rem',
  background: 'var(--motored-surface-alt, #fffbeb)',
});

const listaStyle = { display: 'flex', flexWrap: 'wrap', gap: '0.35rem 0.75rem', margin: '0.35rem 0 0', padding: 0, listStyle: 'none' };

function agrupar(hallazgos) {
  const grupos = new Map();
  for (const h of hallazgos) {
    if (!grupos.has(h.tipo)) grupos.set(h.tipo, []);
    grupos.get(h.tipo).push(h);
  }
  return [...grupos.entries()];
}

function textoDe(hallazgo) {
  if (!TITULOS[hallazgo.tipo]) return hallazgo.mensaje;
  return hallazgo.mensaje.match(CODIGO_ENTRE_COMILLAS)?.[1] || hallazgo.mensaje;
}

function Grupo({ tipo, items }) {
  return (
    <div style={{ marginTop: '0.6rem' }}>
      <strong style={{ fontSize: '0.8rem' }}>{TITULOS[tipo] || 'Otras advertencias'} ({items.length})</strong>
      {AYUDAS[tipo] && <p style={{ margin: '0.15rem 0 0', fontSize: '0.75rem' }}>{AYUDAS[tipo]}</p>}
      <ul style={listaStyle}>
        {items.map((h, i) => <li key={`${tipo}-${i}`} style={{ fontSize: '0.75rem' }}>{textoDe(h)}</li>)}
      </ul>
    </div>
  );
}

export default function AvisosSalud({ hallazgos }) {
  const [abierto, setAbierto] = useState(false);
  if (!hallazgos || hallazgos.length === 0) return null;
  const bloqueante = hallazgos.some((h) => h.bloqueante);
  const total = hallazgos.length;
  const etiqueta = `${total} ${total === 1 ? 'advertencia' : 'advertencias'}`;
  return (
    <div style={cajaStyle(bloqueante)}>
      <button
        type="button"
        className="motored-btn motored-btn-secondary"
        aria-expanded={abierto}
        onClick={() => setAbierto(!abierto)}
      >
        {abierto ? 'Ocultar' : 'Ver'} {etiqueta}
      </button>
      {abierto && agrupar(hallazgos).map(([tipo, items]) => <Grupo key={tipo} tipo={tipo} items={items} />)}
    </div>
  );
}
