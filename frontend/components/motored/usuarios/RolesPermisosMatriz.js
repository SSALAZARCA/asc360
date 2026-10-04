'use client';
/**
 * Usuarios > Roles y permisos: read-only table of role x screen. The data comes
 * from `lib/motored/permisosPorRol.js`; nothing here can be edited.
 */
import MotoredTableScroll from '../MotoredTableScroll';
import InfoTooltip from '../InfoTooltip';
import { ROLES, PANTALLAS, tienePermiso } from '../../../lib/motored/permisosPorRol';

const thStyle = { padding: '0 12px 8px 0', whiteSpace: 'nowrap', textAlign: 'center', fontWeight: 700 };
const stickyStyle = {
  position: 'sticky', left: 0, zIndex: 1, textAlign: 'left', whiteSpace: 'nowrap',
  background: 'var(--motored-surface, #ffffff)', padding: '10px 12px 10px 0', fontWeight: 600,
};
const celdaStyle = { padding: '10px 12px 10px 0', textAlign: 'center' };
const notaStyle = { padding: '10px 0', fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)', minWidth: '14rem' };

function Marca({ si }) {
  return (
    <span
      role="img" aria-label={si ? 'Sí' : 'No'}
      style={{ fontWeight: 700, color: si ? 'var(--motored-success, #15803d)' : 'var(--motored-text-soft, #8a8a8a)' }}
    >
      {si ? '✓' : '—'}
    </span>
  );
}

export default function RolesPermisosMatriz() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', minWidth: 0 }}>
      <h3 className="motored-h-seccion">Roles y permisos</h3>
      <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Vista de solo lectura. Los permisos se definen en la aplicación; para cambiarlos, contacte al administrador del sistema.
      </p>
      <MotoredTableScroll>
        <table aria-label="Roles y permisos" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
          <thead>
            <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
              <th scope="col" style={{ ...stickyStyle, padding: '0 12px 8px 0' }}>Pantalla</th>
              {ROLES.map((rol) => (
                <th key={rol.id} scope="col" style={thStyle}>
                  {rol.id} <InfoTooltip text={rol.ayuda} />
                </th>
              ))}
              <th scope="col" style={{ ...thStyle, textAlign: 'left' }}>Nota</th>
            </tr>
          </thead>
          <tbody>
            {PANTALLAS.map((pantalla) => (
              <tr key={pantalla.id} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
                <th scope="row" style={stickyStyle}>{pantalla.nombre}</th>
                {ROLES.map((rol) => (
                  <td key={rol.id} style={celdaStyle}><Marca si={tienePermiso(pantalla.id, rol.id)} /></td>
                ))}
                <td style={notaStyle}>{pantalla.nota}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </MotoredTableScroll>
    </div>
  );
}
