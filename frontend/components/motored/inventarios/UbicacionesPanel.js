'use client';
/**
 * "Ubicaciones (opcional)" (WU11): pairs create locations while counting;
 * the leader may also prepare the bins before or while counting. The code never changes (its label may be printed); the
 * name can be renamed and a location deactivated. GERENCIA only reads.
 */
import { useState } from 'react';
import MotoredTableScroll from '../MotoredTableScroll';
import { cardStyle, errorStyle, h2Style, labelStyle, monoStyle, mutedStyle, tdStyle, thStyle, touchStyle } from './estilos';

function NuevaUbicacion({ ubicaciones }) {
  const [codigo, setCodigo] = useState('');
  const [nombre, setNombre] = useState('');
  const agregar = async (evento) => {
    evento.preventDefault();
    const payload = { codigo: codigo.trim(), ...(nombre.trim() ? { nombre: nombre.trim() } : {}) };
    if (await ubicaciones.crear(payload)) {
      setCodigo('');
      setNombre('');
    }
  };
  return (
    <form onSubmit={agregar} style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
      <label style={labelStyle}>Código<input value={codigo} maxLength={40} onChange={(e) => setCodigo(e.target.value)} style={touchStyle} placeholder="A3" /></label>
      <label style={labelStyle}>Nombre<input value={nombre} maxLength={60} onChange={(e) => setNombre(e.target.value)} style={touchStyle} placeholder="Estante A3" /></label>
      <button type="submit" className="motored-btn motored-btn-primary" style={{ minHeight: '44px' }} disabled={ubicaciones.ocupado || !codigo.trim()}>
        Agregar
      </button>
    </form>
  );
}

function Fila({ ubicacion, opera, ubicaciones }) {
  const [editando, setEditando] = useState(false);
  const [nombre, setNombre] = useState(ubicacion.nombre);
  const guardar = async () => {
    if (await ubicaciones.renombrar(ubicacion.id, nombre.trim())) setEditando(false);
  };
  const { codigo } = ubicacion;
  return (
    <tr style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)', opacity: ubicacion.activa ? 1 : 0.6 }}>
      <td style={{ ...tdStyle, ...monoStyle, fontWeight: 600 }}>{codigo}</td>
      <td style={tdStyle}>
        {editando ? (
          <input aria-label={`Nuevo nombre de ${codigo}`} value={nombre} maxLength={60} onChange={(e) => setNombre(e.target.value)} style={touchStyle} />
        ) : ubicacion.nombre}
      </td>
      <td style={tdStyle}>{ubicacion.activa ? 'Activa' : 'Inactiva'}{ubicacion.origen === 'PAREJA' ? ' · creada por una pareja' : ''}</td>
      {opera && (
        <td style={tdStyle}>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {editando ? (
              <>
                <button type="button" className="motored-btn motored-btn-primary" disabled={!nombre.trim() || ubicaciones.ocupado} onClick={guardar}>Guardar nombre</button>
                <button type="button" className="motored-btn motored-btn-tertiary" onClick={() => setEditando(false)}>Cancelar</button>
              </>
            ) : (
              <button type="button" className="motored-btn motored-btn-tertiary" aria-label={`Renombrar ${codigo}`} onClick={() => setEditando(true)}>Renombrar</button>
            )}
            <button
              type="button" className="motored-btn motored-btn-tertiary" disabled={ubicaciones.ocupado}
              aria-label={`${ubicacion.activa ? 'Desactivar' : 'Activar'} ${codigo}`}
              onClick={() => ubicaciones.activar(ubicacion.id, !ubicacion.activa)}
            >
              {ubicacion.activa ? 'Desactivar' : 'Activar'}
            </button>
          </div>
        </td>
      )}
    </tr>
  );
}

/** Owner decision 2026-10-09: preparing locations is optional (pairs create
 * them while counting), so the panel starts collapsed. */
export default function UbicacionesPanel({ permisos, ubicaciones }) {
  const { opera } = permisos;
  const [abierto, setAbierto] = useState(false);
  const total = ubicaciones.lista.length;
  return (
    <section style={cardStyle}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem' }}>
        <h2 style={h2Style}>Ubicaciones (opcional)</h2>
        <button
          type="button" className="motored-btn motored-btn-tertiary" aria-expanded={abierto}
          onClick={() => setAbierto((v) => !v)}
        >
          {abierto ? 'Ocultar ubicaciones' : `Mostrar ubicaciones (${total})`}
        </button>
      </div>
      <p style={{ ...mutedStyle, margin: 0 }}>
        Las crean las parejas al contar: antes de escanear escriben dónde están y, si la ubicación no existe, se crea sola.
        Aquí solo puede prepararlas, renombrarlas o desactivarlas si lo necesita.
      </p>
      {abierto && <ListaUbicaciones opera={opera} ubicaciones={ubicaciones} />}
    </section>
  );
}

function ListaUbicaciones({ opera, ubicaciones }) {
  return (
    <>
      {opera && <NuevaUbicacion ubicaciones={ubicaciones} />}
      {ubicaciones.error && <p role="alert" style={errorStyle}>{ubicaciones.error}</p>}
      {ubicaciones.lista.length === 0 ? (
        <p style={{ ...mutedStyle, margin: 0 }}>Todavía no hay ubicaciones.</p>
      ) : (
        <MotoredTableScroll maxHeight="360px">
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
            <thead>
              <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
                <th style={thStyle}>Código</th><th style={thStyle}>Nombre</th><th style={thStyle}>Estado</th>
                {opera && <th style={thStyle}>Acción</th>}
              </tr>
            </thead>
            <tbody>
              {ubicaciones.lista.map((u) => <Fila key={u.id} ubicacion={u} opera={opera} ubicaciones={ubicaciones} />)}
            </tbody>
          </table>
        </MotoredTableScroll>
      )}
    </>
  );
}
