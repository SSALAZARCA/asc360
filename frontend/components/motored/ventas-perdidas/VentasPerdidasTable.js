'use client';
/**
 * frontend/components/motored/ventas-perdidas/VentasPerdidasTable.js
 *
 * sdd/motored-ventas-perdidas-panel, Phase 7 (design D6). Inline row-edit
 * interaction, deliberately NOT a modal (rejected as overkill for a single
 * numeric field) and NOT save-on-blur (an accidental click-away must never
 * silently change a lost-sale total):
 *   - "Editar" turns the Cantidad cell into a number input, replacing that
 *     row's actions with Guardar/Cancelar.
 *   - Enter saves, Escape cancels. Saving requires an explicit action --
 *     there is no `onBlur` handler on the input at all.
 *   - Only one row is in edit mode at a time (mirrors the single
 *     `editandoId` piece of state below).
 * "Anular" uses `window.confirm`, same as `UsuariosTable`'s Desactivar, and
 * `motored-row-action` (never a red button, same rule as `UsuariosTable`).
 * Only an ACTIVA line exposes Editar/Anular -- an ANULADA line is read-only
 * (spec "Only ACTIVA lines are mutable").
 *
 * Deactivated sucursal/asesor (spec "Deactivated sucursal or asesor does
 * not restrict visibility or action"): the line stays visible and fully
 * actionable, just flagged with "(inactiva)"/"(inactivo)" next to the name
 * -- same labelling convention as `VentasPerdidasFilters`'s dropdowns.
 */
import MotoredTableScroll from '../MotoredTableScroll';
import { useState } from 'react';
import VentasPerdidasRow from './VentasPerdidasRow';

const thStyle = { padding: '0 12px 8px 0', textAlign: 'left' };

const LIMITE_BOT_LINEAS = 2000;

export default function VentasPerdidasTable({ lineas, onEditar, onAnular }) {
  const [editandoId, setEditandoId] = useState(null);
  const [valorEdicion, setValorEdicion] = useState('');
  const [errorEdicion, setErrorEdicion] = useState('');

  const iniciarEdicion = (linea) => {
    setEditandoId(linea.linea_id);
    setValorEdicion(String(linea.cantidad));
    setErrorEdicion('');
  };

  const cancelarEdicion = () => {
    setEditandoId(null);
    setValorEdicion('');
    setErrorEdicion('');
  };

  const guardarEdicion = async (lineaId) => {
    const cantidad = Number(valorEdicion);
    if (!(cantidad > 0)) {
      setErrorEdicion('La cantidad debe ser mayor a 0. Para eliminar la línea, usá Anular.');
      return;
    }
    const ok = await onEditar(lineaId, cantidad);
    if (ok !== false) cancelarEdicion();
  };

  const handleAnular = (linea) => {
    if (window.confirm('¿Anular esta línea? La cantidad se revierte del acumulado y no se puede deshacer.')) {
      onAnular(linea.linea_id);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <MotoredTableScroll>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
          <thead>
            <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
              <th style={thStyle}>Fecha</th>
              <th style={thStyle}>Sucursal</th>
              <th style={thStyle}>Asesor</th>
              <th style={thStyle}>Referencia</th>
              <th style={thStyle}>Cantidad</th>
              <th style={thStyle}>Método</th>
              <th style={thStyle}>Estado</th>
              <th style={thStyle}>Editado</th>
              <th style={thStyle}>Anulado</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {lineas.map((linea) => (
              <VentasPerdidasRow
                key={linea.linea_id}
                linea={linea}
                editando={editandoId === linea.linea_id}
                bloqueadoPorOtraEdicion={editandoId !== null && editandoId !== linea.linea_id}
                valorEdicion={valorEdicion}
                errorEdicion={errorEdicion}
                onIniciarEdicion={() => iniciarEdicion(linea)}
                onCambiarValor={setValorEdicion}
                onGuardar={() => guardarEdicion(linea.linea_id)}
                onCancelar={cancelarEdicion}
                onAnular={() => handleAnular(linea)}
              />
            ))}
          </tbody>
        </table>
      </MotoredTableScroll>
      {lineas.length === LIMITE_BOT_LINEAS && (
        <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.75rem' }}>
          Se alcanzó el límite de {LIMITE_BOT_LINEAS} filas. Angostá los filtros para ver el resto.
        </p>
      )}
    </div>
  );
}
