'use client';
import { useState } from 'react';
import { COLOR } from '../tokens';
import { etiquetaTiendas, resumenTiendas } from '../periodo';
import FilterPopover from './FilterPopover';
import { chip } from './estilos';

const normalizar = (texto) => texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

function Casilla({ tienda, activa, onPick }) {
  return (
    <button
      type="button" role="checkbox" aria-checked={activa} onClick={onPick}
      style={{
        fontFamily: 'inherit', fontSize: 13, textAlign: 'left', minHeight: 36, padding: '6px 8px', border: 0, borderRadius: 8,
        background: activa ? COLOR.wash : COLOR.surface, color: COLOR.ink, display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 16, height: 16, flex: 'none', borderRadius: 4, border: `1.5px solid ${activa ? COLOR.ink : COLOR.gray400}`,
          background: activa ? COLOR.ink : COLOR.surface, color: '#FFFFFF', fontSize: 11, lineHeight: '13px', textAlign: 'center',
        }}
      >
        {activa ? '✓' : ''}
      </span>
      {tienda.nombre}
    </button>
  );
}

export default function TiendasFilter({ opciones, filtros, onChange, abierto, onToggle, onClose }) {
  const [busqueda, setBusqueda] = useState('');
  const { tiendas } = opciones;
  const elegidas = filtros.sucursales;
  const visibles = tiendas.filter((t) => normalizar(t.nombre).includes(normalizar(busqueda)));
  const alternar = (id) => onChange({ sucursales: elegidas.includes(id) ? elegidas.filter((x) => x !== id) : [...elegidas, id] });
  return (
    <FilterPopover
      rotulo="Punto de venta" valor={etiquetaTiendas(elegidas, tiendas)} dialogo="Elegir puntos de venta"
      abierto={abierto} onToggle={onToggle} onClose={onClose} resumen={resumenTiendas(elegidas.length, tiendas.length)}
    >
      <button type="button" aria-pressed={elegidas.length === 0} onClick={() => onChange({ sucursales: [] })} style={{ ...chip(elegidas.length === 0), textAlign: 'left' }}>
        Toda la red
      </button>
      <input
        type="search" aria-label="Buscar tienda" placeholder="Buscar tienda…" value={busqueda} onChange={(e) => setBusqueda(e.target.value)}
        style={{ fontFamily: 'inherit', fontSize: 13, height: 36, border: `1px solid ${COLOR.line}`, borderRadius: 8, padding: '0 10px', color: COLOR.ink, background: COLOR.surface }}
      />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 240, overflowY: 'auto', paddingRight: 4 }}>
        {visibles.map((t) => <Casilla key={t.id} tienda={t} activa={elegidas.includes(t.id)} onPick={() => alternar(t.id)} />)}
        {visibles.length === 0 && <span style={{ fontSize: 12.5, color: COLOR.muted, padding: 8 }}>Ninguna tienda coincide.</span>}
      </div>
    </FilterPopover>
  );
}
