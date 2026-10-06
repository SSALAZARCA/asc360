'use client';
import { useState } from 'react';
import { COLOR } from '../tokens';
import { etiquetaTiendas } from '../periodo';
import FilterPopover from './FilterPopover';
import { BOTON_FILTRO, chip } from './estilos';

const normalizar = (texto) => texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const TODOS = 'Todos los asesores';

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

function Quitar({ onClick }) {
  return (
    <button
      type="button" aria-label="Quitar asesor y volver a todos" onClick={onClick}
      style={{ ...BOTON_FILTRO, width: 40, padding: 0, justifyContent: 'center' }}
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true">
        <path d="M6 6l12 12M18 6L6 18" />
      </svg>
    </button>
  );
}

/** Header filter "Asesor": a searchable list "Nombre · Tienda" (it follows the store filter) with an ✕ to go back to everyone. */
export default function AsesorFilter({ lista, opciones, filtros, onChange, abierto, onToggle, onClose }) {
  const [busqueda, setBusqueda] = useState('');
  const asesores = lista ?? [];
  const elegido = asesores.find((a) => a.cedula === filtros.asesor);
  const buscado = normalizar(busqueda);
  const visibles = asesores.filter((a) => normalizar(`${a.nombre} ${a.cedula}`).includes(buscado));
  const elegir = (cedula) => { onChange({ asesor: cedula }); onClose(); };
  return (
    <FilterPopover
      rotulo="Asesor" valor={elegido ? etiquetaAsesor(elegido) : filtros.asesor ? 'Asesor' : TODOS} dialogo="Elegir asesor" ancho={320}
      abierto={abierto} onToggle={onToggle} onClose={onClose}
      resumen={`${asesores.length} ${asesores.length === 1 ? 'asesor' : 'asesores'} · ${etiquetaTiendas(filtros.sucursales, opciones.tiendas)}`}
      acciones={filtros.asesor ? <Quitar onClick={() => onChange({ asesor: null })} /> : null}
    >
      <button type="button" aria-pressed={!filtros.asesor} onClick={() => elegir(null)} style={{ ...chip(!filtros.asesor), textAlign: 'left' }}>
        {TODOS}
      </button>
      <input
        type="search" aria-label="Buscar asesor" placeholder="Buscar por nombre o cédula…" value={busqueda} onChange={(e) => setBusqueda(e.target.value)}
        style={{ fontFamily: 'inherit', fontSize: 13, height: 36, border: `1px solid ${COLOR.line}`, borderRadius: 8, padding: '0 10px', color: COLOR.ink, background: COLOR.surface }}
      />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 250, overflowY: 'auto', paddingRight: 4 }}>
        {visibles.map((a) => <Opcion key={a.cedula} asesor={a} activo={a.cedula === filtros.asesor} onPick={() => elegir(a.cedula)} />)}
        {visibles.length === 0 && <span style={{ fontSize: 12.5, color: COLOR.muted, padding: 8 }}>{lista ? 'Ningún asesor coincide.' : 'Cargando asesores…'}</span>}
      </div>
    </FilterPopover>
  );
}
