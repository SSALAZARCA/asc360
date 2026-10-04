'use client';
/**
 * Manual edit panel of one asesor's budget (add, change or remove). Every save
 * creates a new version of the month; the panel says so. Saving is delegated to
 * `onGuardar`, which rejects with the server message on failure.
 */
import { useState } from 'react';
import { labelStyle, optionStyle, panelStyle, errorStyle, mutedStyle } from './formato';

const TITULOS = { agregar: 'Agregar asesor', editar: 'Editar asesor', quitar: 'Quitar asesor' };
const MONTO_MAXIMO = 100000000000;

export default function EditorAsesor({ modo, linea, tiendas, onGuardar, onCancelar }) {
  const [cedula, setCedula] = useState(linea?.cedula || '');
  const [sucursalId, setSucursalId] = useState(linea?.sucursal_id || '');
  const [monto, setMonto] = useState(linea ? String(linea.monto) : '');
  const [nota, setNota] = useState('');
  const [error, setError] = useState(null);
  const [guardando, setGuardando] = useState(false);
  const quitando = modo === 'quitar';

  const enviar = async (evento) => {
    evento.preventDefault();
    const importe = Number(monto);
    if (!quitando) {
      if (!cedula.trim()) return setError('Ingresa la cédula del asesor.');
      if (!sucursalId) return setError('Elige la tienda del asesor.');
      if (Number.isInteger(importe) && importe > MONTO_MAXIMO) {
        return setError('El presupuesto no puede superar 100.000.000.000 pesos.');
      }
      if (!Number.isInteger(importe) || importe <= 0) {
        return setError('El monto debe ser un número entero de pesos mayor a 0.');
      }
    }
    setError(null);
    setGuardando(true);
    try {
      await onGuardar({ cedula: cedula.trim(), sucursal_id: sucursalId, monto: importe, nota: nota.trim() });
    } catch (e) {
      setError(e.message || 'No se pudo guardar el cambio.');
      setGuardando(false);
    }
  };

  return (
    <form onSubmit={enviar} style={panelStyle} aria-label={TITULOS[modo]}>
      <strong style={{ fontSize: '0.85rem' }}>
        {TITULOS[modo]}{quitando && linea ? `: ${linea.asesor}` : ''}
      </strong>
      {!quitando && (
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <label style={labelStyle} htmlFor="presupuesto-cedula">
            Cédula
            <input id="presupuesto-cedula" value={cedula} readOnly={modo === 'editar'}
              onChange={(e) => setCedula(e.target.value)} />
          </label>
          <label style={labelStyle} htmlFor="presupuesto-tienda">
            Tienda
            <select id="presupuesto-tienda" value={sucursalId} onChange={(e) => setSucursalId(e.target.value)}>
              <option value="" style={optionStyle}>Selecciona una tienda</option>
              {tiendas.map((t) => (
                <option key={t.id} value={t.id} style={optionStyle}>{t.nombre}</option>
              ))}
            </select>
          </label>
          <label style={labelStyle} htmlFor="presupuesto-monto">
            Monto
            <input id="presupuesto-monto" type="number" min="1" step="1" value={monto}
              onChange={(e) => setMonto(e.target.value)} />
          </label>
        </div>
      )}
      <label style={{ ...labelStyle, maxWidth: '32rem' }} htmlFor="presupuesto-nota">
        Nota (opcional)
        <input id="presupuesto-nota" value={nota} maxLength={500} onChange={(e) => setNota(e.target.value)} />
      </label>
      {error && <p role="alert" style={errorStyle}>{error}</p>}
      <p style={mutedStyle}>Se guarda como una versión nueva; la anterior queda en el historial.</p>
      <div style={{ display: 'flex', gap: '0.5rem' }}>
        <button type="submit" className="motored-btn motored-btn-primary" disabled={guardando}>
          {quitando ? 'Quitar asesor' : 'Guardar cambio'}
        </button>
        <button type="button" className="motored-btn motored-btn-secondary" onClick={onCancelar}>Cancelar</button>
      </div>
    </form>
  );
}
