'use client';
/**
 * Side panel with the audit trail: the timeline of the tienda pedido, or, when
 * a line is given, the edits of that line (oldest first).
 */
import { useEffect, useState } from 'react';
import { getEventosTienda, getHistorialLinea } from '../../../lib/motored/pedidosApi';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';
import { etiquetaEvento, etiquetaMotivoEdicion, fechaHora, unidades } from './formato';
import { errorStyle, mutedStyle } from './styles';

const panelStyle = {
  position: 'fixed', top: 0, right: 0, bottom: 0, width: 'min(420px, 100vw)', zIndex: 50, overflowY: 'auto',
  background: 'var(--motored-surface, #ffffff)', borderLeft: '1px solid var(--motored-border, #e4e4e7)',
  padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem', boxShadow: '-4px 0 16px rgba(0,0,0,0.15)',
};

function detalleEvento(e) {
  if (e.evento === 'ENVIADO' && e.detalle?.numero) return `Orden ${e.detalle.numero}`;
  if (e.evento === 'ENVIO_CORREGIDO' && e.detalle) return `Número de orden: ${e.detalle.antes} → ${e.detalle.despues}`;
  return e.motivo || '';
}

function ItemEvento({ e }) {
  return (
    <li>
      <strong>{etiquetaEvento(e.evento)}</strong>{e.usuario && ` · ${e.usuario}`}
      <div style={mutedStyle}>{fechaHora(e.creado_en)}</div>
      {detalleEvento(e) && <div style={{ fontSize: '0.8rem' }}>{detalleEvento(e)}</div>}
    </li>
  );
}

function ItemEdicion({ h }) {
  return (
    <li>
      <strong>{`${unidades(h.valor_anterior)} → ${unidades(h.valor_nuevo)}`}</strong>{` · ${etiquetaMotivoEdicion(h.motivo)}`}
      <div style={mutedStyle}>{`${h.usuario} · ${fechaHora(h.creado_en)}`}</div>
    </li>
  );
}

export default function HistorialDrawer({ corridaId, sucursalId, linea, onClose }) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState('');
  const lineaId = linea?.id;

  useEffect(() => {
    let activo = true;
    const carga = lineaId ? getHistorialLinea(corridaId, lineaId) : getEventosTienda(corridaId, sucursalId);
    carga
      .then((filas) => { if (activo) setItems(filas); })
      .catch((err) => { if (activo) setError(mensajeConCodigo(err, 'No se pudo cargar el historial.')); });
    return () => { activo = false; };
  }, [corridaId, sucursalId, lineaId]);

  const titulo = linea ? `Historial de ${linea.codigo_referencia}` : 'Historial del pedido';
  return (
    <aside role="dialog" aria-label={titulo} style={panelStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0, fontSize: '1rem' }}>{titulo}</h2>
        <button type="button" className="motored-btn motored-btn-secondary" aria-label="Cerrar historial" onClick={onClose}>Cerrar</button>
      </div>
      {error && <p role="alert" style={errorStyle}>{error}</p>}
      {!error && items === null && <p style={mutedStyle}>Cargando...</p>}
      {items && items.length === 0 && <p style={mutedStyle}>Sin movimientos</p>}
      {items && items.length > 0 && (
        <ul style={{ margin: 0, paddingLeft: '1.1rem', display: 'flex', flexDirection: 'column', gap: '0.6rem', fontSize: '0.85rem' }}>
          {items.map((it) => (linea ? <ItemEdicion key={it.id} h={it} /> : <ItemEvento key={it.id} e={it} />))}
        </ul>
      )}
    </aside>
  );
}
