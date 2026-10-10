'use client';
/**
 * The expanded detail of one reference on the leader panel
 * (odd/tasks/motored-conteo-panel-busqueda.md): the counted quantity per
 * location, which pair counted it, in which round and when. Fetched on
 * demand when the row opens, and again when the panel version moves
 * (`base`). The leader is not blind: quantities are shown.
 */
import { useEffect, useState } from 'react';
import * as api from '../../../lib/motored/conteosApi';
import { formatCantidad, formatHora } from './conteosFormato';
import { errorStyle, monoStyle, mutedStyle } from './estilos';

const th = {
  textAlign: 'left', padding: '6px 8px', fontSize: '0.7rem', textTransform: 'uppercase',
  color: 'var(--motored-text-muted, #5a5a5a)', fontWeight: 700,
};
const td = { padding: '6px 8px', borderTop: '1px solid var(--motored-border, #e4e4e7)' };
const tdNum = { ...td, ...monoStyle, textAlign: 'right', whiteSpace: 'nowrap' };

const RONDAS = { 1: 'Primera vuelta', 2: 'Reconteo' };

export default function DetalleReferencia({ conteoId, codigo, base }) {
  const [estado, setEstado] = useState({ cargando: true });

  useEffect(() => {
    let vigente = true;
    api.obtenerDetalleDiferencia(conteoId, codigo)
      .then((datos) => { if (vigente) setEstado({ datos }); })
      .catch((err) => { if (vigente) setEstado({ error: err.message || 'No se pudo cargar el detalle.' }); });
    return () => { vigente = false; };
  }, [conteoId, codigo, base]);

  if (estado.error) return <p role="alert" style={{ ...errorStyle, margin: 0 }}>{estado.error}</p>;
  if (!estado.datos) return <p style={{ ...mutedStyle, margin: 0 }}>Cargando detalle…</p>;
  const { lineas } = estado.datos;
  if (lineas.length === 0) return <p style={{ ...mutedStyle, margin: 0 }}>Nadie ha contado esta referencia todavía.</p>;
  return (
    <div style={{ overflowX: 'auto' }}>
      <table aria-label={`Detalle de ${codigo}`} style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
        <thead>
          <tr>
            <th style={th}>Ubicación</th><th style={th}>Pareja</th><th style={th}>Vuelta</th>
            <th style={{ ...th, textAlign: 'right' }}>Cantidad</th><th style={{ ...th, textAlign: 'right' }}>Última lectura</th>
          </tr>
        </thead>
        <tbody>
          {lineas.map((l) => (
            <tr key={`${l.ubicacion}|${l.ronda}|${l.sesion.id}`}>
              <td style={td}>{l.ubicacion}</td>
              <td style={td}>{l.sesion.etiqueta || '—'}</td>
              <td style={td}>{RONDAS[l.ronda] ?? l.ronda}</td>
              <td style={tdNum}>{formatCantidad(l.cantidad)}</td>
              <td style={tdNum}>{formatHora(l.ultima_lectura_en)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
