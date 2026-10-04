'use client';
/** Side drawer with every saved version of one setting, newest first. */
import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { formatearValor } from './valor';
import { errorStyle, mutedStyle, touchStyle } from './styles';

const drawerStyle = {
  position: 'fixed', top: 0, right: 0, bottom: 0, zIndex: 60, width: 'min(520px, 100vw)',
  background: 'var(--motored-surface, #ffffff)', borderLeft: '1px solid var(--motored-border, #e4e4e7)',
  boxShadow: '-8px 0 24px rgba(0, 0, 0, 0.18)', padding: '1.25rem', overflowY: 'auto',
  display: 'flex', flexDirection: 'column', gap: '1rem', boxSizing: 'border-box',
};
const celdaStyle = { padding: '6px 10px 6px 0', textAlign: 'left', verticalAlign: 'top' };

const mes = (fecha) => (fecha ? fecha.slice(0, 7) : '—');
const instante = (texto) => (texto ? texto.replace('T', ' ').slice(0, 16) : '—');

function Fila({ spec, version }) {
  return (
    <tr>
      <td style={celdaStyle}>{mes(version.vigente_desde)}</td>
      <td style={celdaStyle}>{formatearValor(spec, version.valor)}</td>
      <td style={celdaStyle}>{version.sucursal_id ? 'Una tienda' : 'Todas las tiendas'}</td>
      <td style={celdaStyle}>{version.created_by_nombre || '—'}</td>
      <td style={celdaStyle}>{instante(version.created_at)}</td>
    </tr>
  );
}

function Tabla({ spec, versiones }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ fontSize: '0.8rem', borderCollapse: 'collapse', width: '100%' }}>
        <thead>
          <tr>
            {['Rige desde', 'Valor', 'Alcance', 'Creado por', 'Fecha de creación'].map((t) => (
              <th key={t} className="motored-t-rotulo" style={celdaStyle}>{t}</th>
            ))}
          </tr>
        </thead>
        <tbody>{versiones.map((v) => <Fila key={v.id} spec={spec} version={v} />)}</tbody>
      </table>
    </div>
  );
}

export default function HistorialDrawer({ spec, etiqueta, cargar, onCerrar }) {
  const [versiones, setVersiones] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let vigente = true;
    cargar(spec.clave)
      .then((filas) => { if (vigente) setVersiones(filas); })
      .catch((err) => { if (vigente) setError(err.message || 'No se pudo cargar el historial.'); });
    return () => { vigente = false; };
  }, [cargar, spec.clave]);

  return (
    <aside role="dialog" aria-label={`Historial de ${etiqueta}`} style={drawerStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.5rem' }}>
        <h2 className="motored-h-pantalla" style={{ fontSize: '1rem', margin: 0 }}>{`Historial: ${etiqueta}`}</h2>
        <button type="button" aria-label="Cerrar" className="motored-btn motored-btn-secondary" style={touchStyle} onClick={onCerrar}>
          <X size={16} aria-hidden="true" />
        </button>
      </div>
      {error && <p role="alert" style={errorStyle}>{error}</p>}
      {!error && versiones === null && <p style={mutedStyle}>Cargando...</p>}
      {versiones && versiones.length === 0 && <p style={mutedStyle}>Aún no hay cambios guardados: rige el valor por defecto.</p>}
      {versiones && versiones.length > 0 && <Tabla spec={spec} versiones={versiones} />}
    </aside>
  );
}
