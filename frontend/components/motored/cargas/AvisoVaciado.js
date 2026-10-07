'use client';
/**
 * Warning of a VENTAS carga that replaces the whole month: the tiendas
 * missing from the file lose that month's sales on Aplicar, and annulling
 * the carga does not bring them back. The "Entiendo" checkbox is the
 * explicit acknowledgement Aplicar waits for. When the planned purge cannot
 * be read, the same acknowledgement is asked for.
 */
import { textoVaciado } from './ventasErp';

const avisoStyle = {
  margin: 0, padding: '0.75rem', fontSize: '0.85rem', fontWeight: 700,
  color: 'var(--motored-danger, #c0392b)', background: 'var(--motored-danger-bg, #fdecea)',
  border: '1px solid var(--motored-danger, #c0392b)', borderRadius: 'var(--motored-radius-sm, 4px)',
};

const SIN_DATOS = 'No se pudo verificar si esta carga borra ventas de otras tiendas. '
  + 'Si el archivo reemplaza el mes completo, Aplicar borra las ventas de ese mes de las tiendas que no vienen en él.';

export default function AvisoVaciado({ vaciado, entendido, onEntendido }) {
  if (!vaciado.requiereConfirmar) return null;
  return (
    <div role="alert" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <p style={avisoStyle}>{vaciado.error ? SIN_DATOS : textoVaciado(vaciado.filas)}</p>
      <label style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.85rem', cursor: 'pointer' }}>
        <input
          type="checkbox" aria-label="Entiendo que se borran esas ventas" checked={entendido}
          style={{ width: '24px', height: '24px', margin: '10px' }} onChange={(e) => onEntendido(e.target.checked)}
        />
        Entiendo que se borran esas ventas
      </label>
    </div>
  );
}
