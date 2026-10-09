/**
 * Location bar, always first: the current bin location in big letters and
 * "Cambiar ubicación". Without a location the code field is open, since
 * nothing can be counted before. A scanned `UBI-…` label in the main field
 * also changes it (handled upstream).
 */
import { useState } from 'react';
import { C, MONO, botonContorno, campo } from './estilos';

function Selector({ ubicaciones, ocupado, onFijar, onCancelar }) {
  const [codigo, setCodigo] = useState('');
  const filtro = codigo.trim().toUpperCase();
  const sugeridas = ubicaciones
    .filter((u) => !filtro || u.codigo.toUpperCase().includes(filtro) || u.nombre.toUpperCase().includes(filtro))
    .slice(0, 8);
  const fijar = async (valor) => {
    if (!valor.trim()) return;
    if (await onFijar(valor.trim())) setCodigo('');
  };
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '100%' }}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          fijar(codigo);
        }}
        style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}
      >
        <label style={{ flex: '1 1 220px', display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13, fontWeight: 700, color: C.vino }}>
          Código de la ubicación
          <input
            type="text"
            autoFocus
            autoComplete="off"
            placeholder="Escanee la etiqueta o escriba, p. ej. A3"
            value={codigo}
            onChange={(e) => setCodigo(e.target.value)}
            style={{ ...campo, fontFamily: MONO }}
          />
        </label>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <button type="submit" disabled={ocupado} style={botonContorno}>Fijar ubicación</button>
          {onCancelar && (
            <button type="button" onClick={onCancelar} style={{ ...botonContorno, borderColor: C.bordeCampo, color: C.tinta }}>
              Cancelar
            </button>
          )}
        </div>
      </form>
      {sugeridas.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }} aria-label="Ubicaciones de la tienda">
          {sugeridas.map((u) => (
            <button
              key={u.id}
              type="button"
              onClick={() => fijar(u.codigo)}
              style={{ fontFamily: 'inherit', fontSize: 13, fontWeight: 700, padding: '6px 10px', borderRadius: 999, border: `1px solid ${C.rosaBorde}`, background: C.blanco, color: C.vino, cursor: 'pointer' }}
            >
              {u.nombre}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function BarraUbicacion({ ubicacion, ubicaciones, ocupado, compacta, onCambiar }) {
  const [editando, setEditando] = useState(false);
  const abierta = editando || !ubicacion;
  const fijar = async (codigo) => {
    const ok = await onCambiar(codigo);
    if (ok) setEditando(false);
    return ok;
  };
  return (
    <section
      aria-label="Ubicación"
      style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: compacta ? '12px 14px' : '16px 20px', borderRadius: 12, background: C.rosa, border: `1px solid ${C.rosaBorde}` }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
        <div style={{ fontSize: compacta ? 12 : 13, fontWeight: 700, color: C.vino }}>
          {compacta ? 'Ubicación' : 'Ubicación actual'}
        </div>
        <div
          data-ubicacion-actual
          style={{ fontFamily: MONO, fontSize: compacta ? 20 : 28, fontWeight: 600, color: C.vino, overflowWrap: 'anywhere' }}
        >
          {ubicacion ? (ubicacion.nombre || ubicacion.codigo) : 'Sin ubicación'}
        </div>
      </div>
      {!abierta && (
        <button type="button" onClick={() => setEditando(true)} style={botonContorno}>
          {compacta ? 'Cambiar' : 'Cambiar ubicación'}
        </button>
      )}
      {abierta && (
        <Selector
          ubicaciones={ubicaciones}
          ocupado={ocupado}
          onFijar={fijar}
          onCancelar={ubicacion ? () => setEditando(false) : null}
        />
      )}
    </section>
  );
}
