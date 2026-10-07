'use client';
/**
 * Dry run of a raw ERP VENTAS carga (VALIDADO, before Aplicar): what the
 * load discards (the counters of `log`), the refs without a commercial line
 * (they block Aplicar until each gets one), the rows outside the parts lines
 * and the refs missing from the catalog (they do not block). `estado` is the
 * `useReferenciasSinLinea` state the Resumen tab owns.
 */
import TablaSinLinea from './TablaSinLinea';
import { numeroLegible, resumenContadores, textoNoEncontradas } from './ventasErp';

const mutedStyle = { margin: 0, fontSize: '0.8rem', color: 'var(--motored-text-muted, #5a5a5a)' };
const avisoStyle = {
  margin: 0, padding: '0.5rem 0.75rem', fontSize: '0.8rem', fontWeight: 600,
  color: 'var(--motored-warning, #d97706)', background: 'var(--motored-warning-bg, #fef3e2)',
  borderRadius: 'var(--motored-radius-sm, 4px)',
};
const errorStyle = { margin: 0, fontSize: '0.8rem', color: 'var(--motored-danger, #c0392b)' };
const tituloStyle = { margin: 0, fontSize: '0.9rem', fontWeight: 700 };

function Contadores({ log }) {
  const lineas = resumenContadores(log);
  if (!lineas.length) return null;
  return (
    <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.8rem' }}>
      {lineas.map((t) => <li key={t}>{t}</li>)}
    </ul>
  );
}

function ListaCompacta({ titulo, items }) {
  if (!items.length) return null;
  return (
    <div>
      <p style={{ ...mutedStyle, fontWeight: 600 }}>{titulo}</p>
      <ul style={{ margin: 0, paddingLeft: '1.25rem', columns: '14rem', fontSize: '0.8rem' }}>
        {items.map(([clave, filas]) => <li key={clave}>{`${clave}: ${numeroLegible(filas)} filas`}</li>)}
      </ul>
    </div>
  );
}

function Listas({ datos }) {
  const { fuera_de_linea: fuera = [], no_encontradas: faltan = [] } = datos;
  return (
    <>
      {faltan.length > 0 && <p role="status" style={avisoStyle}>{textoNoEncontradas(faltan)}</p>}
      <ListaCompacta titulo="Referencias que no están en el catálogo" items={faltan.map((r) => [r.codigo, r.filas])} />
      <ListaCompacta titulo="Filas fuera de las líneas de repuestos (no se cargan)" items={fuera.map((r) => [r.linea, r.filas])} />
    </>
  );
}

function SinLinea({ estado, puedeAsignar }) {
  const { datos, aviso, ocupado, lineas, asignarUna, asignarVarias } = estado;
  return (
    <>
      <h3 style={tituloStyle}>Referencias sin línea</h3>
      {aviso && <p role="alert" style={errorStyle}>{aviso}</p>}
      {datos.sin_linea.length
        ? (
          <TablaSinLinea
            filas={datos.sin_linea} puedeAsignar={puedeAsignar} lineas={lineas} ocupado={ocupado}
            asignarUna={asignarUna} asignarVarias={asignarVarias}
          />
        )
        : <p style={mutedStyle}>Todas las referencias del archivo tienen línea.</p>}
    </>
  );
}

export default function PanelVentasErp({ log, estado, puedeAsignar }) {
  const { datos, error, recargar } = estado;
  return (
    <section aria-label="Revisión de ventas del ERP" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <Contadores log={log} />
      {error && (
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <p style={errorStyle}>{error}</p>
          <button type="button" className="motored-btn motored-btn-secondary" style={{ minHeight: '44px' }} onClick={recargar}>
            Reintentar
          </button>
        </div>
      )}
      {!error && !datos && <p style={mutedStyle}>Revisando referencias sin línea...</p>}
      {datos && <SinLinea estado={estado} puedeAsignar={puedeAsignar} />}
      {datos && <Listas datos={datos} />}
    </section>
  );
}
