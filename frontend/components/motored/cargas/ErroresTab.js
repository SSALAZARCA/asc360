'use client';
/**
 * frontend/components/motored/cargas/ErroresTab.js
 *
 * Grilla de errores + CSV + acciones de resolución (sdd/motored-pedidos-
 * ingesta, Phase 10, task 10.2; spec "Error-resolution actions" -- mapear a
 * sucursal existente, crear referencia bajo `OTROS`, o ignorar; y
 * "carga_error model and CSV export" -- descarga vía
 * `descargarErroresCargaCsv`, que ya neutraliza `=+-@` server-side).
 *
 * Paginado en el CLIENTE: `GET /cargas/{id}/errores` no acepta `offset`/
 * `limit` (devuelve la lista completa, ver `backend/app/motored/api/
 * cargas.py::listar_errores`) -- la paginación de la spec es una propiedad
 * de la GRILLA, no del endpoint.
 *
 * Las acciones de resolución escriben server-side (persisten `sucursal_
 * alias` o crean la `referencia`), así que tras cada una se recarga la
 * lista de errores -- una fila resuelta no debería seguir apareciendo como
 * pendiente de acción (aunque el registro histórico del error en sí no se
 * borra, ver `resolver_errores`).
 */
import { useEffect, useState, useCallback } from 'react';
import { getErroresCarga, resolverErroresCarga, descargarErroresCargaCsv, listMaestros } from '../../../lib/motored/api';
import { getRolActual } from '../../../lib/motored/motoredFetch';

const PAGE_SIZE = 50;

function useErrores(cargaId) {
  const [errores, setErrores] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getErroresCarga(cargaId);
      setErrores(data);
    } catch (err) {
      setError(err.message || 'No se pudieron cargar los errores');
    } finally {
      setLoading(false);
    }
  }, [cargaId]);

  useEffect(() => {
    load();
  }, [load]);

  return { errores, loading, error, reload: load };
}

function usePagina(total) {
  const [pagina, setPagina] = useState(0);
  const totalPaginas = Math.max(1, Math.ceil(total / PAGE_SIZE));
  useEffect(() => {
    if (pagina >= totalPaginas) setPagina(0);
  }, [totalPaginas, pagina]);
  return { pagina, setPagina, totalPaginas };
}

function AccionFila({ error: err, puedeEscribir, sucursales, onAccion }) {
  const [sucursalId, setSucursalId] = useState('');

  if (!puedeEscribir) return null;

  if (err.codigo_error === 'SUCURSAL_NO_ENCONTRADA') {
    return (
      <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
        <select value={sucursalId} onChange={(e) => setSucursalId(e.target.value)}>
          <option value="" style={{ color: '#1a1a18' }}>— Mapear a —</option>
          {sucursales.map((s) => (
            <option key={s.id} value={s.id} style={{ color: '#1a1a18' }}>{s.nombre}</option>
          ))}
        </select>
        <button
          type="button" className="motored-row-action"
          onClick={() => onAccion({ codigo_error: err.codigo_error, valor: err.valor, accion: 'mapear_sucursal', sucursal_id: sucursalId })}
          disabled={!sucursalId}
        >
          Mapear
        </button>
        <button
          type="button" className="motored-row-action"
          onClick={() => onAccion({ codigo_error: err.codigo_error, valor: err.valor, accion: 'ignorar' })}
        >
          Ignorar
        </button>
      </div>
    );
  }

  if (err.codigo_error === 'REFERENCIA_NO_ENCONTRADA') {
    return (
      <div style={{ display: 'flex', gap: '0.4rem' }}>
        <button
          type="button" className="motored-row-action"
          onClick={() => onAccion({ codigo_error: err.codigo_error, valor: err.valor, accion: 'crear_referencia' })}
        >
          Crear como OTROS
        </button>
        <button
          type="button" className="motored-row-action"
          onClick={() => onAccion({ codigo_error: err.codigo_error, valor: err.valor, accion: 'ignorar' })}
        >
          Ignorar
        </button>
      </div>
    );
  }

  return (
    <button
      type="button" className="motored-row-action"
      onClick={() => onAccion({ codigo_error: err.codigo_error, valor: err.valor, accion: 'ignorar' })}
    >
      Ignorar
    </button>
  );
}

function ErroresGrid({ pageRows, puedeEscribir, sucursales, onAccion }) {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }} data-testid="errores-grid">
      <thead>
        <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)', textAlign: 'left' }}>
          <th style={{ padding: '0 12px 8px 0' }}>Fila</th>
          <th style={{ padding: '0 12px 8px 0' }}>Columna</th>
          <th style={{ padding: '0 12px 8px 0' }}>Valor</th>
          <th style={{ padding: '0 12px 8px 0' }}>Código</th>
          <th style={{ padding: '0 12px 8px 0' }}>Mensaje</th>
          {puedeEscribir && <th style={{ padding: '0 12px 8px 0' }}>Acción</th>}
        </tr>
      </thead>
      <tbody>
        {pageRows.map((err) => (
          <tr key={err.id} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }} data-testid="error-row">
            <td style={{ padding: '10px 12px 10px 0' }}>{err.fila}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{err.columna || <em>—</em>}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{err.valor || <em>—</em>}</td>
            <td style={{ padding: '10px 12px 10px 0' }} className="motored-mono">{err.codigo_error}</td>
            <td style={{ padding: '10px 12px 10px 0' }}>{err.mensaje}</td>
            {puedeEscribir && (
              <td style={{ padding: '10px 0' }}>
                <AccionFila error={err} puedeEscribir={puedeEscribir} sucursales={sucursales} onAccion={onAccion} />
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Paginacion({ pagina, setPagina, totalPaginas }) {
  if (totalPaginas <= 1) return null;
  return (
    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', fontSize: '0.75rem' }}>
      <button type="button" className="motored-btn motored-btn-secondary" onClick={() => setPagina((p) => Math.max(0, p - 1))} disabled={pagina === 0}>
        Anterior
      </button>
      <span>Página {pagina + 1} de {totalPaginas}</span>
      <button type="button" className="motored-btn motored-btn-secondary" onClick={() => setPagina((p) => Math.min(totalPaginas - 1, p + 1))} disabled={pagina >= totalPaginas - 1}>
        Siguiente
      </button>
    </div>
  );
}

export default function ErroresTab({ carga }) {
  const { errores, loading, error, reload } = useErrores(carga.id);
  const [rol, setRol] = useState(null);
  const [sucursales, setSucursales] = useState([]);
  const [accionError, setAccionError] = useState('');
  const [csvError, setCsvError] = useState('');
  const { pagina, setPagina, totalPaginas } = usePagina(errores.length);

  useEffect(() => {
    setRol(getRolActual());
    listMaestros('sucursales').then(setSucursales).catch(() => setSucursales([]));
  }, []);

  const puedeEscribir = rol === 'ADMIN' || rol === 'COMPRAS';

  const handleAccion = async (accion) => {
    setAccionError('');
    try {
      await resolverErroresCarga(carga.id, [accion]);
      await reload();
    } catch (err) {
      setAccionError(err.message || 'No se pudo aplicar la acción');
    }
  };

  const handleDescargarCsv = async () => {
    setCsvError('');
    try {
      await descargarErroresCargaCsv(carga.id);
    } catch (err) {
      setCsvError(err.message || 'No se pudo descargar el CSV');
    }
  };

  if (error) return <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{error}</p>;

  const pageRows = errores.slice(pagina * PAGE_SIZE, (pagina + 1) * PAGE_SIZE);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          {errores.length} error(es) encontrado(s)
        </p>
        <button type="button" className="motored-btn motored-btn-secondary" onClick={handleDescargarCsv} disabled={errores.length === 0}>
          Descargar CSV
        </button>
      </div>

      {csvError && <p style={{ margin: 0, color: 'var(--motored-danger, #c0392b)', fontSize: '0.75rem' }}>{csvError}</p>}
      {accionError && <p style={{ margin: 0, color: 'var(--motored-danger, #c0392b)', fontSize: '0.75rem' }}>{accionError}</p>}

      {loading ? (
        <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>Cargando...</p>
      ) : errores.length === 0 ? (
        <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>Sin errores — todas las filas pasaron.</p>
      ) : (
        <>
          <ErroresGrid pageRows={pageRows} puedeEscribir={puedeEscribir} sucursales={sucursales} onAccion={handleAccion} />
          <Paginacion pagina={pagina} setPagina={setPagina} totalPaginas={totalPaginas} />
        </>
      )}
    </div>
  );
}
