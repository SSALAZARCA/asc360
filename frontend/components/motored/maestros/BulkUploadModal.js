'use client';
/**
 * frontend/components/motored/maestros/BulkUploadModal.js
 *
 * Bulk-upload flow for one masters entity (sdd/motored-pedidos-cimientos,
 * Phase 6, task 6.3/6.4, design ADR-6). The backend contract (`backend/app/
 * motored/api/carga.py`) is unchanged and still deliberately simple per the
 * proposal's locked scope: `filas` is an array of already-structured row
 * objects, not a raw file (Fase 1 "carga masiva" is a small synchronous
 * JSON-rows upload, not the §5/§9 streaming pipeline).
 *
 * What changed: the FIRST version of this modal asked a business user to
 * type that JSON array by hand -- unusable, per direct user feedback ("no
 * dice como se carga... por eso carece de toda usabilidad"). This version
 * lets them pick the real CSV file exported from Excel; parsing happens
 * here in the browser (via `papaparse`, not `xlsx`/SheetJS -- SheetJS's
 * npm-published build carries an unpatched ReDoS advisory with no fix
 * available, and this use case is plain tabular data with no need for
 * `.xlsx`'s binary format or formula support) and the parsed rows are sent
 * to the exact same backend endpoint as before. A live preview table and a
 * downloadable template make the expected columns concrete instead of
 * asking the user to infer them.
 *
 * Owner decision #1 (all-or-nothing) means a `carga`/`validar` response can
 * be `{ ok: false, errores: [{ fila, motivo }, ...] }` with MULTIPLE rows
 * reported at once (never fail-fast) -- this component's one hard
 * requirement (task 6.4) is to render EVERY row in `errores`, not just a
 * generic "upload failed" banner.
 */
import { useState } from 'react';
import Papa from 'papaparse';
import { validarCarga, subirCarga } from '../../../lib/motored/api';

// Columnas esperadas por maestro -- hoy solo `sucursal` tiene pantalla real
// (SucursalesTab.js); se completa acá mismo el día que se agreguen
// Bodegas/Proveedores/Referencias. `aliases` es case/acento-insensible:
// cubre variantes razonables del encabezado tal como puede venir de Excel.
const COLUMNAS_POR_ENTIDAD = {
  sucursal: [
    { key: 'nombre', label: 'Nombre', required: true, aliases: ['nombre', 'sucursal'] },
    { key: 'sic', label: 'SIC', required: false, aliases: ['sic'] },
    {
      key: 'dias_seguridad', label: 'Días de seguridad', required: false,
      aliases: ['dias_seguridad', 'dias seguridad', 'días de seguridad', 'días seguridad'],
    },
  ],
};

function normalizeHeader(header) {
  return header
    .normalize('NFD').replace(/[̀-ͯ]/g, '') // saca tildes
    .trim().toLowerCase();
}

function buildColumnMap(entidad, rawHeaders) {
  const spec = COLUMNAS_POR_ENTIDAD[entidad] || [];
  const normalizedHeaders = rawHeaders.map(normalizeHeader);
  const map = {}; // rawHeader -> canonicalKey
  spec.forEach((col) => {
    const idx = normalizedHeaders.findIndex((h) => col.aliases.includes(h));
    if (idx !== -1) map[rawHeaders[idx]] = col.key;
  });
  return map;
}

function rowsToCanonical(entidad, parsedRows, rawHeaders) {
  const columnMap = buildColumnMap(entidad, rawHeaders);
  return parsedRows.map((row) => {
    const canonical = {};
    Object.entries(row).forEach(([rawHeader, value]) => {
      const key = columnMap[rawHeader];
      if (key) canonical[key] = typeof value === 'string' ? value.trim() : value;
    });
    return canonical;
  });
}

function missingRequiredColumns(entidad, rawHeaders) {
  const spec = COLUMNAS_POR_ENTIDAD[entidad] || [];
  const columnMap = buildColumnMap(entidad, rawHeaders);
  const presentKeys = new Set(Object.values(columnMap));
  return spec.filter((col) => col.required && !presentKeys.has(col.key)).map((col) => col.label);
}

function downloadTemplate(entidad) {
  const spec = COLUMNAS_POR_ENTIDAD[entidad] || [];
  const csv = Papa.unparse({ fields: spec.map((c) => c.label), data: [] });
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `plantilla_${entidad}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function useCargaMasiva(entidad, onSuccess) {
  const [fileName, setFileName] = useState('');
  const [filas, setFilas] = useState([]);
  const [parseError, setParseError] = useState('');
  const [resultado, setResultado] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleFile = (file) => {
    setResultado(null);
    setParseError('');
    setFilas([]);
    if (!file) return;
    setFileName(file.name);

    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        const rawHeaders = results.meta.fields || [];
        const faltantes = missingRequiredColumns(entidad, rawHeaders);
        if (faltantes.length > 0) {
          setParseError(`Al archivo le falta la columna obligatoria: ${faltantes.join(', ')}`);
          return;
        }
        setFilas(rowsToCanonical(entidad, results.data, rawHeaders));
      },
      error: (err) => setParseError(`No se pudo leer el archivo: ${err.message}`),
    });
  };

  const runWith = async (apiFn, { notifyOnSuccess } = {}) => {
    if (filas.length === 0) return;
    setLoading(true);
    setResultado(null);
    try {
      const res = await apiFn(entidad, filas);
      setResultado(res);
      if (notifyOnSuccess && res.ok) onSuccess?.(res);
    } catch (err) {
      setResultado({ ok: false, errores: [{ fila: 0, motivo: err.message }] });
    } finally {
      setLoading(false);
    }
  };

  return {
    fileName, filas, parseError, resultado, loading, handleFile,
    runValidar: () => runWith(validarCarga),
    runCarga: () => runWith(subirCarga, { notifyOnSuccess: true }),
  };
}

function ColumnasEsperadas({ entidad }) {
  const spec = COLUMNAS_POR_ENTIDAD[entidad] || [];
  return (
    <div style={{ fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
      Columnas que debe tener el archivo (primera fila = encabezados):
      <ul style={{ margin: '0.35rem 0 0', paddingLeft: '1.1rem' }}>
        {spec.map((col) => (
          <li key={col.key}>
            <strong style={{ color: 'var(--motored-text, #1a1a18)' }}>{col.label}</strong>
            {col.required ? ' (obligatoria)' : ' (opcional)'}
          </li>
        ))}
      </ul>
    </div>
  );
}

function FilePicker({ fileName, onFile }) {
  return (
    <label
      style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        gap: '0.4rem', padding: '1.5rem', border: '2px dashed var(--motored-border, #e4e4e7)',
        borderRadius: 'var(--motored-radius-md, 8px)', background: 'var(--motored-surface-alt, #f4f4f5)',
        cursor: 'pointer', textAlign: 'center',
      }}
    >
      <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--motored-text, #1a1a18)' }}>
        {fileName || 'Hacé clic acá para elegir el archivo CSV'}
      </span>
      <span style={{ fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        En Excel: Archivo → Guardar como → tipo &quot;CSV (delimitado por comas)&quot;
      </span>
      <input
        type="file"
        accept=".csv,text/csv"
        style={{ display: 'none' }}
        onChange={(e) => onFile(e.target.files?.[0])}
      />
    </label>
  );
}

function FilasPreview({ filas }) {
  if (filas.length === 0) return null;
  const columnas = Object.keys(filas[0]);
  return (
    <div>
      <p style={{ margin: '0 0 0.5rem', fontSize: '0.75rem', fontWeight: 700, color: 'var(--motored-text, #1a1a18)' }}>
        Vista previa — {filas.length} fila(s) leídas del archivo
      </p>
      <div style={{ maxHeight: '160px', overflow: 'auto', border: '1px solid var(--motored-border, #e4e4e7)', borderRadius: '6px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.75rem' }}>
          <thead>
            <tr style={{ background: 'var(--motored-surface-alt, #f4f4f5)' }}>
              {columnas.map((c) => (
                <th key={c} style={{ textAlign: 'left', padding: '0.4rem 0.6rem' }}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filas.slice(0, 20).map((fila, idx) => (
              <tr key={idx} style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
                {columnas.map((c) => (
                  <td key={c} style={{ padding: '0.4rem 0.6rem' }}>{String(fila[c] ?? '')}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filas.length > 20 && (
        <p style={{ margin: '0.35rem 0 0', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          Mostrando las primeras 20 de {filas.length} filas.
        </p>
      )}
    </div>
  );
}

function CargaResultPanel({ resultado }) {
  if (!resultado) return null;

  if (resultado.ok) {
    return (
      <div style={{ color: 'var(--motored-success, #15803d)', fontSize: '0.8rem', fontWeight: 700 }}>
        OK — {resultado.total_filas} filas procesadas
        {typeof resultado.insertados === 'number' && ` (${resultado.insertados} nuevas, ${resultado.actualizados} actualizadas)`}
      </div>
    );
  }

  return (
    <div>
      <p style={{ margin: '0 0 0.5rem', color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem', fontWeight: 700 }}>
        Archivo rechazado — {resultado.errores?.length ?? 0} fila(s) con error. No se escribió nada.
      </p>
      <ul data-testid="carga-error-list" style={{ margin: 0, padding: '0 0 0 1.25rem', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
        {(resultado.errores || []).map((err, idx) => (
          <li
            key={`${err.fila}-${idx}`}
            data-testid="carga-error-row"
            style={{ color: 'var(--motored-text, #1a1a18)', fontSize: '0.75rem' }}
          >
            Fila {err.fila}: {err.motivo}
          </li>
        ))}
      </ul>
    </div>
  );
}

const overlayStyle = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200,
};

const boxStyle = {
  background: 'var(--motored-surface, #ffffff)',
  border: '1px solid var(--motored-border, #e4e4e7)',
  borderRadius: 'var(--motored-radius-md, 8px)',
  padding: '1.5rem', width: '100%', maxWidth: '640px', maxHeight: '90vh',
  overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem',
};

export default function BulkUploadModal({ entidad, onClose, onSuccess }) {
  const { fileName, filas, parseError, resultado, loading, handleFile, runValidar, runCarga } =
    useCargaMasiva(entidad, onSuccess);

  return (
    <div role="dialog" aria-label={`Carga masiva de ${entidad}`} style={overlayStyle}>
      <div style={boxStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 800, color: 'var(--motored-text, #1a1a18)' }}>
            Carga masiva — {entidad}
          </h2>
          <button type="button" className="motored-btn motored-btn-tertiary" onClick={() => downloadTemplate(entidad)}>
            Descargar plantilla CSV
          </button>
        </div>

        <ColumnasEsperadas entidad={entidad} />

        <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          Todo-o-nada: si una sola fila del archivo es inválida, no se escribe nada.
        </p>

        <FilePicker fileName={fileName} onFile={handleFile} />

        {parseError && (
          <p style={{ margin: 0, color: 'var(--motored-danger, #c0392b)', fontSize: '0.75rem' }}>{parseError}</p>
        )}

        <FilasPreview filas={filas} />

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button type="button" className="motored-btn motored-btn-secondary" onClick={runValidar} disabled={loading || filas.length === 0}>
            {loading ? 'Validando...' : 'Validar'}
          </button>
          <button type="button" className="motored-btn motored-btn-primary" onClick={runCarga} disabled={loading || filas.length === 0}>
            {loading ? 'Cargando...' : 'Cargar'}
          </button>
          <button type="button" className="motored-btn motored-btn-tertiary" onClick={onClose} disabled={loading}>
            Cerrar
          </button>
        </div>

        <CargaResultPanel resultado={resultado} />
      </div>
    </div>
  );
}
