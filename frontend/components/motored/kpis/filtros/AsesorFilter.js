'use client';
import { useEffect, useState } from 'react';
import { COLOR } from '../tokens';
import { etiquetaTiendas } from '../periodo';
import FilterPopover from './FilterPopover';

const normalizar = (texto) => texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

/** `Nombre · Tienda` as the pill and the list name it. */
export const etiquetaAsesor = (a) => (a.tienda ? `${a.nombre} · ${a.tienda}` : a.nombre);

function Opcion({ asesor, activo, onPick }) {
  return (
    <button
      type="button" aria-pressed={activo} onClick={onPick}
      style={{
        fontFamily: 'inherit', fontSize: 13, textAlign: 'left', minHeight: 40, padding: '6px 8px', border: 0, borderRadius: 8,
        background: activo ? COLOR.wash : COLOR.surface, color: COLOR.ink, display: 'flex', flexDirection: 'column', gap: 1, cursor: 'pointer',
      }}
    >
      <span style={{ fontWeight: 700, color: COLOR.ink }}>{asesor.nombre}</span>
      {asesor.tienda && <span style={{ fontSize: 11.5, color: COLOR.muted }}>{asesor.tienda}</span>}
    </button>
  );
}

/** Header filter "Asesor": a required single-select (searchable, "Nombre · Tienda") that follows the filters; it always has one chosen. */
export default function AsesorFilter({ lista, elegido, opciones, filtros, onElegir, abierto, onToggle, onClose }) {
  const [busqueda, setBusqueda] = useState('');
  // Each opening starts with an empty search, so a search typed earlier never hides the list.
  useEffect(() => { if (abierto) setBusqueda(''); }, [abierto]);
  const asesores = lista ?? [];
  const actual = asesores.find((a) => a.cedula === elegido);
  const buscado = normalizar(busqueda);
  const visibles = asesores.filter((a) => normalizar(`${a.nombre} ${a.cedula}`).includes(buscado));
  const elegir = (cedula) => { onElegir(cedula); onClose(); };
  return (
    <FilterPopover
      rotulo="Asesor" valor={actual ? etiquetaAsesor(actual) : 'Asesor'} dialogo="Elegir asesor" ancho={320}
      abierto={abierto} onToggle={onToggle} onClose={onClose}
      resumen={`${asesores.length} ${asesores.length === 1 ? 'asesor' : 'asesores'} · ${etiquetaTiendas(filtros.sucursales, opciones.tiendas)}`}
    >
      <input
        type="search" aria-label="Buscar asesor" placeholder="Buscar por nombre o cédula…" value={busqueda} onChange={(e) => setBusqueda(e.target.value)}
        style={{ fontFamily: 'inherit', fontSize: 13, height: 36, border: `1px solid ${COLOR.line}`, borderRadius: 8, padding: '0 10px', color: COLOR.ink, background: COLOR.surface }}
      />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 250, overflowY: 'auto', paddingRight: 4 }}>
        {visibles.map((a) => <Opcion key={a.cedula} asesor={a} activo={a.cedula === elegido} onPick={() => elegir(a.cedula)} />)}
        {visibles.length === 0 && <span style={{ fontSize: 12.5, color: COLOR.muted, padding: 8 }}>{lista ? 'Ningún asesor coincide.' : 'Cargando asesores…'}</span>}
      </div>
    </FilterPopover>
  );
}
