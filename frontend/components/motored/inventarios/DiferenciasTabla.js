'use client';
/**
 * "Diferencias, de mayor a menor valor" (WU12): the filters Todas /
 * Críticas / En reconteo (counts from the API, filtering on the full list
 * with the backend's own rules), critical rows highlighted, and in
 * EN_RECONTEO "Repartir automático". At most MAX_FILAS rows are drawn so a
 * long first round stays light on a tablet; the Excel has every row.
 *
 * odd/tasks/motored-conteo-panel-busqueda.md: the "Contadas (N)" chip (N
 * from the panel summary) and the search box read every reference of the
 * conteo from the server on demand (`useBusquedaDiferencias`); the search
 * combines with the active chip. Each row opens its per-location detail.
 */
import { useState } from 'react';
import MotoredTableScroll from '../MotoredTableScroll';
import { formatPesos } from './conteosFormato';
import DiferenciaFila from './DiferenciaFila';
import useBusquedaDiferencias from './useBusquedaDiferencias';
import { errorStyle, h2Style, mutedStyle, thStyle, touchStyle } from './estilos';

export const MAX_FILAS = 200;

const FILTROS = [
  { id: 'todas', label: 'Todas', cuenta: 'total', incluye: () => true },
  { id: 'criticas', label: 'Críticas', cuenta: 'criticas', incluye: (f) => f.critico },
  { id: 'reconteo', label: 'En reconteo', cuenta: 'en_reconteo', incluye: (f) => f.reconteo != null },
  { id: 'contadas', label: 'Contadas', cuenta: 'contadas', incluye: () => true },
];

const filtroStyle = (activo) => ({
  minHeight: '44px', padding: '0 12px', borderRadius: '8px', fontWeight: activo ? 700 : 600, cursor: 'pointer',
  border: `1px solid ${activo ? 'var(--motored-text, #1a1a18)' : 'var(--motored-border, #e4e4e7)'}`,
  background: activo ? 'var(--motored-text, #1a1a18)' : 'var(--motored-surface, #ffffff)',
  color: activo ? 'var(--motored-surface, #ffffff)' : 'var(--motored-text, #1a1a18)',
});
const busquedaStyle = {
  ...touchStyle, width: '100%', padding: '0 12px', borderRadius: '8px', fontSize: '0.9rem',
  border: '1px solid var(--motored-border, #e4e4e7)', background: 'var(--motored-surface, #ffffff)',
  color: 'var(--motored-text, #1a1a18)',
};
const th = (alinear = 'left') => ({ ...thStyle, textAlign: alinear, padding: '10px 8px' });

function mensajeVacio(filtro, buscando) {
  if (buscando) return 'Ninguna referencia coincide con la búsqueda.';
  if (filtro === 'contadas') return 'Todavía no hay referencias contadas.';
  return 'No hay diferencias en este filtro.';
}

function Cuerpo({ filas, cargando, error, vacio, umbrales, enReconteo, abierta, onAlternar, ...resto }) {
  if (error) return <p role="alert" style={{ ...errorStyle, margin: '1rem 1.25rem' }}>{error}</p>;
  if (cargando) return <p style={{ ...mutedStyle, margin: '1rem 1.25rem' }}>Cargando diferencias…</p>;
  if (filas.length === 0) return <p style={{ ...mutedStyle, margin: '1rem 1.25rem' }}>{vacio}</p>;
  return (
    <MotoredTableScroll maxHeight="70vh">
      <table style={{ width: '100%', minWidth: '860px', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
        <thead>
          <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.75rem', textTransform: 'uppercase' }}>
            <th style={{ ...th(), paddingLeft: '1.25rem' }}>Referencia</th><th style={th()}>Ubicaciones</th>
            <th style={th('right')}>Sistema</th><th style={th('right')}>Contado</th><th style={th('right')}>Valor dif.</th>
            <th style={th()}>Estado</th><th style={{ ...th('right'), paddingRight: '1.25rem' }}>Acción</th>
          </tr>
        </thead>
        <tbody>
          {filas.slice(0, MAX_FILAS).map((f) => (
            <DiferenciaFila
              key={f.codigo} fila={f} umbrales={umbrales} enReconteo={enReconteo}
              abierta={abierta === f.codigo} onAlternar={onAlternar} {...resto}
            />
          ))}
        </tbody>
      </table>
    </MotoredTableScroll>
  );
}

export default function DiferenciasTabla({ conteo, diferencias, contadas, opera, ocupado, onRepartir, ...acciones }) {
  const [filtro, setFiltro] = useState('todas');
  const [texto, setTexto] = useState('');
  // The code whose detail row is open (one at a time).
  const [abierta, setAbierta] = useState(null);
  const remoto = useBusquedaDiferencias(conteo.id, filtro, texto, diferencias);
  const enReconteo = conteo.estado === 'EN_RECONTEO';
  const actual = FILTROS.find((f) => f.id === filtro);
  const filas = remoto.activa ? (remoto.datos?.items ?? []) : (diferencias?.items ?? []).filter(actual.incluye);
  const umbrales = diferencias?.umbrales ?? conteo.umbrales ?? {};
  const cuentas = { ...diferencias, contadas: remoto.datos?.contadas ?? contadas };
  const alternar = (codigo) => setAbierta((previa) => (previa === codigo ? null : codigo));

  return (
    <div style={{ flex: '999 1 640px', minWidth: 0, background: 'var(--motored-surface, #ffffff)', border: '1px solid var(--motored-border, #e4e4e7)', borderRadius: '12px', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', padding: '1rem 1.25rem', borderBottom: '1px solid var(--motored-border, #e4e4e7)' }}>
        <h2 style={h2Style}>Diferencias, de mayor a menor valor</h2>
        <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
          {FILTROS.map((f) => (
            <button key={f.id} type="button" style={filtroStyle(f.id === filtro)} aria-pressed={f.id === filtro} onClick={() => setFiltro(f.id)}>
              {`${f.label} (${cuentas?.[f.cuenta] ?? 0})`}
            </button>
          ))}
          {opera && enReconteo && (
            <button type="button" className="motored-btn motored-btn-secondary" style={{ minHeight: '44px' }} disabled={ocupado} onClick={onRepartir}>
              Repartir automático
            </button>
          )}
        </div>
        <input
          type="search" aria-label="Buscar referencia" placeholder="Buscar por código o nombre…" value={texto}
          style={busquedaStyle} onChange={(e) => setTexto(e.target.value)}
        />
      </div>
      <Cuerpo
        filas={filas} cargando={diferencias == null || remoto.buscando} error={remoto.error}
        vacio={mensajeVacio(filtro, texto.trim() !== '')} umbrales={umbrales} enReconteo={enReconteo}
        abierta={abierta} onAlternar={alternar} conteoId={conteo.id} base={diferencias}
        opera={opera} ocupado={ocupado} {...acciones}
      />
      {filas.length > MAX_FILAS && (
        <p style={{ ...mutedStyle, margin: '0.5rem 1.25rem' }}>
          Se muestran {MAX_FILAS} de {filas.length}. {remoto.activa ? 'Refina la búsqueda para ver otras.' : 'El Excel de avance trae todas.'}
        </p>
      )}
      <div style={{ ...mutedStyle, padding: '0.75rem 1.25rem', borderTop: '1px solid var(--motored-border, #e4e4e7)', fontSize: '0.8rem' }}>
        Reconteo automático desde {formatPesos(umbrales.reconteo)} · Crítica desde {formatPesos(umbrales.critico)} · Valor al costo promedio de la foto · El reconteo lo hace siempre otra pareja
        {diferencias?.parcial ? ' · Primera vuelta en curso: lo no contado aparece como faltante' : ''}
      </div>
    </div>
  );
}
