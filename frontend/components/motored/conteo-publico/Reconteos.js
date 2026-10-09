/**
 * Reconteo tasks of this pair: code, name and where to look. The API sends
 * no quantities and none are shown (blind count). Counting a task tags its
 * readings with `reconteo_id`; finishing with no readings means "not found".
 */
import { useState } from 'react';
import { C, MONO, botonContorno, tarjeta } from './estilos';

const ESTADOS = { ASIGNADO: 'Pendiente', TERMINADO: 'Terminado' };

function Tarea({ tarea, activa, onElegir }) {
  return (
    <li style={{ listStyle: 'none', padding: '14px 20px', borderBottom: '1px solid #f0f0f2', display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', justifyContent: 'space-between' }}>
      <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
        <span style={{ fontFamily: MONO, fontWeight: 600, fontSize: 15 }}>{tarea.codigo}</span>
        {tarea.descripcion && <span style={{ fontSize: 13, color: C.medio }}>{tarea.descripcion}</span>}
        <span style={{ fontSize: 13 }}>{`Dónde buscar: ${(tarea.ubicaciones || []).join(', ') || 'sin ubicación registrada'}`}</span>
      </div>
      {tarea.estado === 'ASIGNADO' && !activa && (
        <button type="button" onClick={() => onElegir(tarea.id)} style={botonContorno}>Contar este reconteo</button>
      )}
      {(tarea.estado !== 'ASIGNADO' || activa) && (
        <span style={{ fontSize: 13, fontWeight: 800, padding: '4px 10px', borderRadius: 999, background: activa ? C.okFondo : C.fondo, color: activa ? C.ok : C.medio }}>
          {activa ? 'Contando ahora' : (ESTADOS[tarea.estado] || tarea.estado)}
        </span>
      )}
    </li>
  );
}

export function ListaReconteos({ tareas, tareaActivaId, onElegir }) {
  if (!tareas.length) {
    return <div style={{ padding: '14px 20px', fontSize: 14, color: C.medio }}>No tiene reconteos asignados.</div>;
  }
  return (
    <ul aria-label="Reconteos asignados" style={{ ...tarjeta, margin: 0, padding: 0 }}>
      {tareas.map((t) => (
        <Tarea key={t.id} tarea={t} activa={t.id === tareaActivaId} onElegir={onElegir} />
      ))}
    </ul>
  );
}

export function TareaActiva({ tarea, onTerminar, onSoltar }) {
  const [confirmando, setConfirmando] = useState(false);
  const [terminando, setTerminando] = useState(false);
  if (!tarea) return null;
  const terminar = async () => {
    setTerminando(true);
    await onTerminar(tarea.id);
    setTerminando(false);
    setConfirmando(false);
  };
  return (
    <section aria-label="Reconteo activo" style={{ padding: '14px 18px', borderRadius: 12, background: C.alertaFondo, color: C.alerta, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ fontWeight: 800 }}>
        {`Reconteo de ${tarea.codigo}`}
        {tarea.descripcion ? ` · ${tarea.descripcion}` : ''}
      </div>
      <div style={{ fontSize: 13 }}>{`Dónde buscar: ${(tarea.ubicaciones || []).join(', ')}`}</div>
      {!confirmando ? (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button type="button" onClick={() => setConfirmando(true)} style={botonContorno}>Terminar reconteo</button>
          <button type="button" onClick={onSoltar} style={{ ...botonContorno, borderColor: C.bordeCampo, color: C.tinta }}>
            Dejar este reconteo
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 14 }}>
            {`¿Terminar el reconteo de ${tarea.codigo}? Si no encontró unidades, termínelo igual: queda como no encontrado.`}
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button type="button" disabled={terminando} onClick={terminar} style={botonContorno}>Sí, terminar</button>
            <button type="button" onClick={() => setConfirmando(false)} style={{ ...botonContorno, borderColor: C.bordeCampo, color: C.tinta }}>
              Cancelar
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
