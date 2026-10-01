'use client';
/**
 * frontend/components/motored/maestros/VendedoresTable.js
 *
 * Tabla del maestro de vendedores y la lista "Vendedores sin registrar" (gente
 * que aparece vendiendo en las ventas pero no está en el maestro). Ambas van
 * dentro de `MotoredTableScroll` para que scrollen solas en una tablet.
 */
import MotoredTableScroll from '../MotoredTableScroll';
import MotoredIconAction from '../MotoredIconAction';

const th = { padding: '0 12px 8px 0' };
const td = { padding: '10px 12px 10px 0' };
const headRow = { textAlign: 'left', color: 'var(--motored-text-muted, #5a5a5a)' };
const bodyRow = { borderTop: '1px solid var(--motored-border, #e4e4e7)' };

export function VendedoresTable({ vendedores, onEdit, onDeactivate, onReactivate }) {
  const confirmar = (mensaje, accion) => { if (window.confirm(mensaje)) accion(); };
  return (
    <MotoredTableScroll>
      <table aria-label="Vendedores" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={headRow}>
            <th style={th}>Nombre vendedor</th>
            <th style={th}>Cargo</th>
            <th style={th}>Sucursal</th>
            <th style={th}>Cédula</th>
            <th style={th}>Usuario</th>
            <th style={th}>Estado</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {vendedores.map((v) => (
            <tr key={v.id} style={bodyRow}>
              <td style={td}>{v.nombre}</td>
              <td style={td}>{v.cargo}</td>
              <td style={td}>{v.sucursal_nombre || '—'}</td>
              <td style={td}>{v.cedula || '—'}</td>
              <td style={td}>{v.usuario_nombre || '—'}</td>
              <td style={td}>{v.activo ? 'Activo' : 'Inactivo'}</td>
              <td style={{ display: 'flex', gap: '1rem', padding: '10px 0' }}>
                <MotoredIconAction action="Editar" onClick={() => onEdit(v)} touch />
                {v.activo ? (
                  <MotoredIconAction
                    action="Desactivar" touch
                    onClick={() => confirmar(`¿Desactivar a "${v.nombre}"? No se elimina, queda marcado como inactivo.`, () => onDeactivate(v.id))}
                  />
                ) : (
                  <MotoredIconAction
                    action="Reactivar" touch
                    onClick={() => confirmar(`¿Reactivar a "${v.nombre}"? Queda marcado como activo.`, () => onReactivate(v.id))}
                  />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </MotoredTableScroll>
  );
}

export function VendedoresSinRegistrar({ items, error, onAgregar }) {
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <h3 className="motored-h-seccion">Vendedores sin registrar</h3>
      <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Personas que aparecen vendiendo en los archivos de ventas pero no están en el maestro. Mientras no las
        registres, sus ventas cuentan como &quot;resto de compañía&quot; en el tablero.
      </p>
      {error && <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{error}</p>}
      {items.length === 0 && !error ? (
        <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          Todos los vendedores que aparecen en las ventas ya están registrados.
        </p>
      ) : (
        <MotoredTableScroll>
          <table aria-label="Vendedores sin registrar" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={headRow}>
                <th style={th}>Nombre en el ERP</th>
                <th style={th}>Última venta</th>
                <th style={th}>Líneas de venta</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.vendedor_norm} style={bodyRow}>
                  <td style={td}>{it.vendedor_ejemplo}</td>
                  <td style={td}>{it.ultima_venta || '—'}</td>
                  <td style={td}>{it.lineas}</td>
                  <td style={{ padding: '6px 0' }}>
                    <button
                      type="button" className="motored-btn motored-btn-secondary"
                      aria-label={`Agregar ${it.vendedor_ejemplo}`}
                      onClick={() => onAgregar(it)}
                    >
                      Agregar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </MotoredTableScroll>
      )}
    </section>
  );
}
