'use client';
/**
 * frontend/components/motored/ventas-perdidas/VentasPerdidasRow.js
 *
 * sdd/motored-ventas-perdidas-panel, Phase 7 fix-up (gga: `VentasPerdidasTable`
 * mixed edit-state management, validation, confirmation and per-row rendering
 * in one ~130-line function). Extracted here as a pure presentational row --
 * ALL edit state/handlers stay owned by `VentasPerdidasTable`, passed down as
 * props, so this component has no state of its own and no behavior change
 * from the original inline version.
 */
import MotoredIconAction from '../MotoredIconAction';

const tdStyle = { padding: '10px 12px 10px 0' };
const badgeStyle = { marginLeft: '0.4rem', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' };

function formatFechaHora(iso) {
  return iso ? new Date(iso).toLocaleString('es-CO') : '—';
}

export default function VentasPerdidasRow({
  linea,
  editando,
  bloqueadoPorOtraEdicion,
  valorEdicion,
  errorEdicion,
  onIniciarEdicion,
  onCambiarValor,
  onGuardar,
  onCancelar,
  onAnular,
}) {
  const esActiva = linea.estado === 'ACTIVA';

  return (
    <tr style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
      <td style={tdStyle}>{linea.fecha}</td>
      <td style={tdStyle}>
        {linea.sucursal.nombre}
        {!linea.sucursal.activa && <span style={badgeStyle}>(inactiva)</span>}
      </td>
      <td style={tdStyle}>
        {linea.asesor.nombre}
        {!linea.asesor.activo && <span style={badgeStyle}>(inactivo)</span>}
      </td>
      <td style={tdStyle}>{linea.referencia.codigo} — {linea.referencia.nombre}</td>
      {editando ? (
        <td style={tdStyle}>
          <input
            type="number"
            min="1"
            max="9999"
            value={valorEdicion}
            autoFocus
            onChange={(e) => onCambiarValor(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onGuardar();
              if (e.key === 'Escape') onCancelar();
            }}
          />
          {errorEdicion && (
            <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.7rem', margin: '4px 0 0' }}>{errorEdicion}</p>
          )}
        </td>
      ) : (
        <td style={tdStyle} className="motored-mono">{linea.cantidad}</td>
      )}
      <td style={tdStyle}>{linea.metodo || '—'}</td>
      <td style={tdStyle}>{linea.estado}</td>
      <td style={tdStyle}>{linea.editado_por ? `${linea.editado_por.nombre} — ${formatFechaHora(linea.editado_en)}` : '—'}</td>
      <td style={tdStyle}>{linea.anulado_por ? `${linea.anulado_por.nombre} — ${formatFechaHora(linea.anulado_en)}` : '—'}</td>
      <td style={{ padding: '10px 0', display: 'flex', gap: '0.5rem' }}>
        {editando && (
          <>
            <MotoredIconAction action="Guardar" onClick={onGuardar} />
            <MotoredIconAction action="Cancelar" onClick={onCancelar} />
          </>
        )}
        {esActiva && !editando && !bloqueadoPorOtraEdicion && (
          <MotoredIconAction action="Editar" onClick={onIniciarEdicion} />
        )}
        {esActiva && !editando && !bloqueadoPorOtraEdicion && (
          <MotoredIconAction action="Anular" onClick={onAnular} />
        )}
      </td>
    </tr>
  );
}
