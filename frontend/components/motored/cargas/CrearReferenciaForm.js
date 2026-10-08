'use client';
/**
 * frontend/components/motored/cargas/CrearReferenciaForm.js
 *
 * "Crear referencia" for a REFERENCIA_NO_ENCONTRADA row of the Errores tab:
 * the línea comercial (required, from the configured lines of the carga,
 * `GET /cargas/{id}/lineas-comerciales`) and the proveedor (active ones,
 * the principal proveedor HMCL preselected). Says how many rows of this
 * carga share the code, so the user knows what one creation fixes.
 */
import { useEffect, useState } from 'react';
import { getLineasComercialesCarga, listMaestros } from '../../../lib/motored/api';
import InfoTooltip from '../InfoTooltip';

const OPCION = { color: '#1a1a18' };

const overlayStyle = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  zIndex: 200, padding: '16px',
};

const boxStyle = {
  background: 'var(--motored-surface, #ffffff)',
  border: '1px solid var(--motored-border, #e4e4e7)',
  borderRadius: 'var(--motored-radius-md, 8px)',
  padding: '1.5rem', width: '100%', maxWidth: '440px', maxHeight: '90vh',
  overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem',
};

const labelStyle = {
  display: 'flex', flexDirection: 'column', gap: '0.3rem',
  fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)',
};

const AYUDA_LINEA = 'La línea comercial con la que se agrupa la referencia en ventas, indicadores y comisiones. '
  + 'Solo se ofrecen las líneas configuradas en Configuración.';
const AYUDA_PROVEEDOR = 'Quién vende esta referencia. Por defecto es HMCL, el proveedor principal; '
  + 'cámbielo solo si la referencia es de otro proveedor.';

function useOpciones(cargaId) {
  const [lineas, setLineas] = useState([]);
  const [proveedores, setProveedores] = useState([]);
  const [error, setError] = useState('');
  useEffect(() => {
    getLineasComercialesCarga(cargaId)
      .then((data) => setLineas(data || []))
      .catch(() => setError('No se pudieron cargar las líneas comerciales.'));
    listMaestros('proveedores')
      .then((data) => setProveedores((data || []).filter((p) => p.activa !== false)))
      .catch(() => setError('No se pudieron cargar los proveedores.'));
  }, [cargaId]);
  return { lineas, proveedores, error };
}

function textoFilas(cantidad) {
  return cantidad === 1
    ? 'Se resuelve 1 fila de esta carga con este código'
    : `Se resuelven ${cantidad} filas de esta carga con este código`;
}

export default function CrearReferenciaForm({ cargaId, error: err, filasAfectadas, onCrear, onCancelar }) {
  const { lineas, proveedores, error } = useOpciones(cargaId);
  const [linea, setLinea] = useState('');
  const [proveedorId, setProveedorId] = useState('');
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    if (proveedorId || proveedores.length === 0) return;
    const principal = proveedores.find((p) => p.es_principal) || proveedores[0];
    setProveedorId(principal.id);
  }, [proveedores, proveedorId]);

  const crear = async () => {
    setEnviando(true);
    try {
      await onCrear({
        codigo_error: err.codigo_error,
        valor: err.valor,
        accion: 'crear_referencia',
        linea_comercial: linea,
        // Empty (the list could not load): the server uses the principal proveedor.
        proveedor_id: proveedorId || null,
      });
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div role="dialog" aria-label={`Crear referencia ${err.valor || ''}`} style={overlayStyle}>
      <div style={boxStyle}>
        <h3 className="motored-h-seccion" style={{ margin: 0 }}>Crear referencia {err.valor}</h3>
        <p style={{ margin: 0, fontSize: '0.85rem' }}>{textoFilas(filasAfectadas)}</p>
        <label style={labelStyle}>
          <span>Línea comercial <InfoTooltip text={AYUDA_LINEA} /></span>
          <select value={linea} onChange={(e) => setLinea(e.target.value)} required>
            <option value="" style={OPCION}>— Elija la línea —</option>
            {lineas.map((o) => (
              <option key={o.valor} value={o.valor} style={OPCION}>{o.etiqueta}</option>
            ))}
          </select>
        </label>
        <label style={labelStyle}>
          <span>Proveedor <InfoTooltip text={AYUDA_PROVEEDOR} /></span>
          <select value={proveedorId} onChange={(e) => setProveedorId(e.target.value)}>
            {proveedores.map((p) => (
              <option key={p.id} value={p.id} style={OPCION}>{p.nombre}</option>
            ))}
          </select>
        </label>
        {error && (
          <p role="alert" style={{ margin: 0, color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{error}</p>
        )}
        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
          <button type="button" className="motored-btn motored-btn-secondary" onClick={onCancelar} disabled={enviando}>
            Cancelar
          </button>
          <button
            type="button" className="motored-btn motored-btn-primary"
            onClick={crear} disabled={enviando || !linea}
          >
            Crear referencia
          </button>
        </div>
      </div>
    </div>
  );
}
