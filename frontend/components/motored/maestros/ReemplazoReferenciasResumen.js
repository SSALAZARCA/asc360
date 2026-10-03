'use client';
/**
 * frontend/components/motored/maestros/ReemplazoReferenciasResumen.js
 *
 * Resumen previo (dry-run) de la carga de REFERENCIAS, que reemplaza el
 * maestro completo (motored-referencia-identidad, R2). Lo muestra
 * `BulkUploadModal` después de validar: dice en castellano qué se va a crear,
 * actualizar, mover de proveedor, desactivar (resaltando las que vendieron en
 * los últimos 6 meses o tienen stock) y reactivar, y qué vínculos de sustituta
 * se quitan. Nada se aplica hasta "Confirmar reemplazo"; si se desactiva más
 * del 10% de las activas hay una segunda confirmación explícita.
 */
import { useState } from 'react';

const colorMuted = 'var(--motored-text-muted, #5a5a5a)';
const colorText = 'var(--motored-text, #1a1a18)';
const colorWarning = 'var(--motored-warning, #d97706)';

const estiloLista = { margin: '0.25rem 0 0', paddingLeft: '1.1rem', fontSize: '0.75rem', color: colorText };

function Grupo({ titulo, total, children, destacado = false }) {
  if (!total) return null;
  return (
    <li style={{ fontSize: '0.8rem', color: colorText, marginBottom: '0.5rem' }}>
      <strong style={destacado ? { color: colorWarning } : undefined}>{titulo}</strong>
      {children}
    </li>
  );
}

function Muestra({ items, render, total }) {
  if (!items?.length) return null;
  return (
    <ul style={estiloLista}>
      {items.map((item, idx) => <li key={`${item.codigo}-${idx}`}>{render(item)}</li>)}
      {total > items.length && (
        <li style={{ color: colorMuted }}>… y {total - items.length} más</li>
      )}
    </ul>
  );
}

function motivosDeDesactivacion(item) {
  const motivos = [];
  if (item.con_ventas_6m) motivos.push('vendió en los últimos 6 meses');
  if (item.con_inventario) motivos.push('tiene stock');
  return motivos.join(' y ');
}

function TextoDesactivar({ inactivar }) {
  const destacadas = [];
  if (inactivar.con_ventas_6m) destacadas.push(`${inactivar.con_ventas_6m} vendieron en los últimos 6 meses`);
  if (inactivar.con_inventario) destacadas.push(`${inactivar.con_inventario} tienen stock`);
  return (
    <>
      {destacadas.length > 0 && (
        <p style={{ margin: '0.25rem 0 0', fontSize: '0.75rem', fontWeight: 700, color: colorWarning }}>
          Ojo: {destacadas.join(' y ')}.
        </p>
      )}
      <Muestra
        items={inactivar.muestra} total={inactivar.total}
        render={(item) => {
          const motivo = motivosDeDesactivacion(item);
          return (
            <>
              {item.codigo}{item.nombre ? ` — ${item.nombre}` : ''}
              {motivo && <strong style={{ color: colorWarning }}>{` (${motivo})`}</strong>}
            </>
          );
        }}
      />
    </>
  );
}

function DobleConfirmacion({ resumen, confirmado, onChange }) {
  const pct = Math.round(resumen.pct_inactivar * 100);
  return (
    <label
      style={{
        display: 'flex', gap: '0.6rem', alignItems: 'flex-start', padding: '0.75rem',
        border: `1px solid ${colorWarning}`, borderRadius: '6px', fontSize: '0.8rem', color: colorText,
        minHeight: '44px', cursor: 'pointer',
      }}
    >
      <input
        type="checkbox" checked={confirmado} onChange={(e) => onChange(e.target.checked)}
        style={{ width: '1.25rem', height: '1.25rem', flexShrink: 0 }}
      />
      <span>
        Entiendo que se van a desactivar {resumen.inactivar.total} de {resumen.activas_actuales} referencias
        activas ({pct}%), más del 10%. Si la opción &quot;consolidar sustituidas&quot; está activada, esas
        referencias dejarían de contarse en los pedidos.
      </span>
    </label>
  );
}

function totalCambios(resumen) {
  return resumen.crear.total + resumen.actualizar.total + resumen.mover_proveedor.total
    + resumen.inactivar.total + resumen.reactivar.total;
}

function ListaDeCambios({ resumen }) {
  return (
    <>
      <ul style={{ margin: 0, paddingLeft: '1.1rem' }}>
        <Grupo titulo={`Se crean ${resumen.crear.total} referencias nuevas`} total={resumen.crear.total}>
          <Muestra items={resumen.crear.muestra} total={resumen.crear.total} render={(i) => `${i.codigo} (${i.proveedor})`} />
        </Grupo>
        <Grupo titulo={`Se actualizan ${resumen.actualizar.total} referencias`} total={resumen.actualizar.total}>
          <Muestra
            items={resumen.actualizar.muestra} total={resumen.actualizar.total}
            render={(i) => `${i.codigo}: cambia ${i.campos.join(', ')}`}
          />
        </Grupo>
        <Grupo
          titulo={`Cambian de proveedor ${resumen.mover_proveedor.total} referencias`}
          total={resumen.mover_proveedor.total}
        >
          <Muestra
            items={resumen.mover_proveedor.muestra} total={resumen.mover_proveedor.total}
            render={(i) => `${i.codigo}: ${i.proveedor_anterior} → ${i.proveedor_nuevo}`}
          />
        </Grupo>
        <Grupo
          titulo={`Se desactivan ${resumen.inactivar.total} referencias que no están en el archivo`}
          total={resumen.inactivar.total} destacado
        >
          <TextoDesactivar inactivar={resumen.inactivar} />
        </Grupo>
        <Grupo titulo={`Se reactivan ${resumen.reactivar.total} referencias`} total={resumen.reactivar.total}>
          <Muestra items={resumen.reactivar.muestra} total={resumen.reactivar.total} render={(i) => i.codigo} />
        </Grupo>
        <Grupo
          titulo={`Se quitan ${resumen.vinculos_sustituta_limpiados.total} vínculos de sustituta`}
          total={resumen.vinculos_sustituta_limpiados.total}
        >
          <p style={{ margin: '0.25rem 0 0', fontSize: '0.75rem', color: colorMuted }}>
            Porque la referencia sustituta cambió de proveedor y la sustituta debe ser del mismo proveedor.
          </p>
          <Muestra
            items={resumen.vinculos_sustituta_limpiados.muestra} total={resumen.vinculos_sustituta_limpiados.total}
            render={(i) => `${i.codigo} (sustituta: ${i.sustituta})`}
          />
        </Grupo>
      </ul>
      {totalCambios(resumen) === 0 && (
        <p style={{ margin: 0, fontSize: '0.8rem', color: colorMuted }}>El archivo no cambia nada del maestro actual.</p>
      )}
    </>
  );
}

export default function ReemplazoReferenciasResumen({ resumen, loading, onConfirmar }) {
  const [confirmadoMasivo, setConfirmadoMasivo] = useState(false);
  if (!resumen) return null;

  const requiere = resumen.requiere_doble_confirmacion;
  const bloqueado = loading || (requiere && !confirmadoMasivo);

  return (
    <section
      aria-label="Resumen del reemplazo de referencias"
      style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}
    >
      <p style={{ margin: 0, fontSize: '0.8rem', fontWeight: 700, color: colorText }}>
        Esto es lo que va a pasar con las {resumen.total_archivo} referencias del archivo. Todavía no se aplicó nada.
      </p>
      <ListaDeCambios resumen={resumen} />

      {requiere && (
        <DobleConfirmacion resumen={resumen} confirmado={confirmadoMasivo} onChange={setConfirmadoMasivo} />
      )}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem' }}>
        <button
          type="button" className="motored-btn motored-btn-primary" style={{ minHeight: '44px' }}
          disabled={bloqueado}
          onClick={() => onConfirmar({ confirmarReemplazo: true, confirmarInactivacionMasiva: requiere && confirmadoMasivo })}
        >
          {loading ? 'Aplicando...' : 'Confirmar reemplazo'}
        </button>
      </div>
    </section>
  );
}
