'use client';
/**
 * frontend/components/motored/maestros/ReemplazoReferenciasResumen.js
 *
 * Resumen previo (dry-run) de la carga de REFERENCIAS, que reemplaza el
 * maestro completo (motored-referencia-identidad, R2). Lo muestra
 * `BulkUploadModal` después de validar: dice en castellano qué se va a crear,
 * actualizar, mover de proveedor y reactivar, y qué vínculos de sustituta se
 * quitan. R3: las referencias activas que NO vienen en el archivo (ausentes)
 * se listan con un checkbox "Inactivar" (todas sin marcar: por defecto siguen
 * activas) y solo se inactivan las elegidas; resaltan las que vendieron en los
 * últimos 6 meses o tienen stock. Nada se aplica hasta "Confirmar reemplazo";
 * si lo elegido (más las que quedan inactivas por sustituta) pasa del 10% de
 * las activas hay una segunda confirmación explícita.
 */
import { memo, useMemo, useState } from 'react';

const colorMuted = 'var(--motored-text-muted, #5a5a5a)';
const colorText = 'var(--motored-text, #1a1a18)';
const colorWarning = 'var(--motored-warning, #d97706)';

const UMBRAL_DOBLE_CONFIRMACION = 0.1; // igual que el backend (> 10%)

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

const estiloBoton = { minHeight: '44px', padding: '0 0.75rem', fontSize: '0.75rem' };

const EtiquetaAlerta = ({ children }) => (
  <strong
    style={{
      color: colorWarning, border: `1px solid ${colorWarning}`, borderRadius: '4px',
      padding: '0 0.3rem', fontSize: '0.7rem', whiteSpace: 'nowrap',
    }}
  >
    {children}
  </strong>
);

const FilaAusente = memo(function FilaAusente({ item, marcada, onToggle }) {
  const resaltada = item.con_ventas_6m || item.con_inventario;
  return (
    <li style={{ listStyle: 'none', borderBottom: '1px solid rgba(128,128,128,0.25)' }}>
      <label
        style={{
          display: 'flex', gap: '0.6rem', alignItems: 'center', flexWrap: 'wrap', minHeight: '44px',
          padding: '0.25rem 0.5rem', cursor: 'pointer', fontSize: '0.75rem', color: colorText,
          background: resaltada ? 'rgba(217,119,6,0.12)' : 'transparent',
        }}
      >
        <input
          type="checkbox" checked={marcada} onChange={() => onToggle(item.codigo)}
          aria-label={`Inactivar ${item.codigo}`}
          style={{ width: '1.25rem', height: '1.25rem', flexShrink: 0 }}
        />
        <span style={{ fontWeight: 700 }}>{item.codigo}</span>
        {item.nombre && <span>{item.nombre}</span>}
        {item.proveedor && <span style={{ color: colorMuted }}>{item.proveedor}</span>}
        {item.con_ventas_6m && <EtiquetaAlerta>Vendió en los últimos 6 meses</EtiquetaAlerta>}
        {item.con_inventario && <EtiquetaAlerta>Tiene stock</EtiquetaAlerta>}
      </label>
    </li>
  );
});

function AusentesPanel({ ausentes, seleccion, onToggle, onMarcar }) {
  const items = ausentes.items || [];
  const destacadas = [];
  if (ausentes.con_ventas_6m) destacadas.push(`${ausentes.con_ventas_6m} vendieron en los últimos 6 meses`);
  if (ausentes.con_inventario) destacadas.push(`${ausentes.con_inventario} tienen stock`);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <p style={{ margin: 0, fontSize: '0.8rem', fontWeight: 700, color: colorText }}>
        {ausentes.total} referencias activas no vienen en el archivo
      </p>
      <p style={{ margin: 0, fontSize: '0.75rem', color: colorText }}>
        No vienen en el archivo: por defecto siguen activas. Marcá las que quieras inactivar.
      </p>
      {destacadas.length > 0 && (
        <p style={{ margin: 0, fontSize: '0.75rem', fontWeight: 700, color: colorWarning }}>
          Ojo: {destacadas.join(' y ')}.
        </p>
      )}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
        <button type="button" className="motored-btn" style={estiloBoton} onClick={() => onMarcar('todas')}>
          Marcar todas
        </button>
        <button type="button" className="motored-btn" style={estiloBoton} onClick={() => onMarcar('sin-actividad')}>
          Marcar solo las que no tienen ventas ni inventario
        </button>
        <button type="button" className="motored-btn" style={estiloBoton} onClick={() => onMarcar('ninguna')}>
          Quitar selección
        </button>
      </div>
      <p aria-live="polite" style={{ margin: 0, fontSize: '0.8rem', fontWeight: 700, color: colorText }}>
        Se inactivarán {seleccion.size} de {ausentes.total}
      </p>
      <ul
        aria-label="Referencias ausentes del archivo"
        style={{
          margin: 0, padding: 0, maxHeight: 'min(45vh, 360px)', overflowY: 'auto',
          border: '1px solid rgba(128,128,128,0.4)', borderRadius: '6px',
        }}
      >
        {items.map((item) => (
          <FilaAusente key={item.codigo} item={item} marcada={seleccion.has(item.codigo)} onToggle={onToggle} />
        ))}
      </ul>
    </div>
  );
}

function DobleConfirmacion({ resumen, inactivadas, pct: fraccion, confirmado, onChange }) {
  const pct = Math.round(fraccion * 100);
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
        aria-label="Entiendo la desactivación masiva"
        style={{ width: '1.25rem', height: '1.25rem', flexShrink: 0 }}
      />
      <span>
        Entiendo que se van a desactivar {inactivadas} de {resumen.activas_actuales} referencias
        activas ({pct}%), más del 10%. Si la opción &quot;consolidar sustituidas&quot; está activada, esas
        referencias dejarían de contarse en los pedidos.
      </span>
    </label>
  );
}

const totalPorSustituta = (resumen) => resumen.inactivar_por_sustituta?.total ?? 0;

// Todas las activas que terminan inactivas: las ausentes elegidas + las que quedan con sustituta.
export const totalInactivadas = (resumen) => (resumen.seleccionadas ?? 0) + totalPorSustituta(resumen);

// Lo que cambia SIN que el usuario elija nada (las ausentes siguen activas por defecto).
function totalCambios(resumen) {
  return resumen.crear.total + resumen.actualizar.total + resumen.mover_proveedor.total
    + totalPorSustituta(resumen) + resumen.reactivar.total;
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
          titulo={`Se desactivan ${totalPorSustituta(resumen)} referencias porque el archivo les pone una sustituta`}
          total={totalPorSustituta(resumen)} destacado
        >
          <Muestra
            items={resumen.inactivar_por_sustituta?.muestra} total={totalPorSustituta(resumen)}
            render={(i) => `${i.codigo}${i.nombre ? ` — ${i.nombre}` : ''}`}
          />
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

const SELECCION_VACIA = new Set();

// La selección y la confirmación masiva valen solo para ESTE resumen: se guardan
// junto al resumen al que pertenecen, así uno nuevo (otro archivo o re-validar)
// nace sin nada marcado. Cambiar la selección también desmarca la confirmación.
function useSeleccion(resumen) {
  const [estado, setEstado] = useState({ resumen: null, codigos: SELECCION_VACIA, confirmado: false });
  const vigente = estado.resumen === resumen;
  const codigos = vigente ? estado.codigos : SELECCION_VACIA;
  const confirmado = vigente && estado.confirmado;

  const cambiar = (siguiente) => setEstado({ resumen, codigos: siguiente, confirmado: false });
  const alternar = (codigo) => setEstado((previo) => {
    const base = previo.resumen === resumen ? previo.codigos : SELECCION_VACIA;
    const siguiente = new Set(base);
    if (siguiente.has(codigo)) siguiente.delete(codigo); else siguiente.add(codigo);
    return { resumen, codigos: siguiente, confirmado: false };
  });
  const marcar = (modo) => {
    const items = resumen?.ausentes?.items || [];
    if (modo === 'todas') cambiar(new Set(items.map((i) => i.codigo)));
    else if (modo === 'sin-actividad') {
      cambiar(new Set(items.filter((i) => !i.con_ventas_6m && !i.con_inventario).map((i) => i.codigo)));
    } else cambiar(SELECCION_VACIA);
  };
  const confirmar = (marcado) => setEstado({ resumen, codigos, confirmado: marcado });
  return { codigos, confirmado, alternar, marcar, confirmar };
}

export default function ReemplazoReferenciasResumen({ resumen, loading, onConfirmar }) {
  const { codigos, confirmado, alternar, marcar, confirmar } = useSeleccion(resumen);
  const seleccionado = useMemo(() => ({ ...(resumen || {}), seleccionadas: codigos.size }), [resumen, codigos]);
  if (!resumen) return null;

  // El % sale de la selección actual (el backend lo vuelve a calcular al aplicar).
  const inactivadas = totalInactivadas(seleccionado);
  const pct = resumen.activas_actuales ? inactivadas / resumen.activas_actuales : 0;
  const requiere = pct > UMBRAL_DOBLE_CONFIRMACION;
  const bloqueado = loading || (requiere && !confirmado);

  return (
    <section
      aria-label="Resumen del reemplazo de referencias"
      style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}
    >
      <p style={{ margin: 0, fontSize: '0.8rem', fontWeight: 700, color: colorText }}>
        Esto es lo que va a pasar con las {resumen.total_archivo} referencias del archivo. Todavía no se aplicó nada.
      </p>
      <ListaDeCambios resumen={resumen} />

      {resumen.ausentes?.total > 0 && (
        <AusentesPanel ausentes={resumen.ausentes} seleccion={codigos} onToggle={alternar} onMarcar={marcar} />
      )}

      {requiere && (
        <DobleConfirmacion
          resumen={resumen} inactivadas={inactivadas} pct={pct} confirmado={confirmado} onChange={confirmar}
        />
      )}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem' }}>
        <button
          type="button" className="motored-btn motored-btn-primary" style={{ minHeight: '44px' }}
          disabled={bloqueado}
          onClick={() => onConfirmar({
            confirmarReemplazo: true,
            confirmarInactivacionMasiva: requiere && confirmado,
            codigosInactivar: [...codigos],
          })}
        >
          {loading ? 'Aplicando...' : 'Confirmar reemplazo'}
        </button>
      </div>
    </section>
  );
}
