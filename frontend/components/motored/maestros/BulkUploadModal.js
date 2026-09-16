'use client';
/**
 * frontend/components/motored/maestros/BulkUploadModal.js
 *
 * Bulk-upload flow for one masters entity (sdd/motored-pedidos-cimientos,
 * Phase 6, task 6.3/6.4, design ADR-6). `.csv` still posts JSON rows
 * (`filas: list[dict]`) to the original endpoints, unchanged since Fase 1;
 * `.xlsx` posts the raw file to a separate pair of endpoints added later
 * (see the second doc block below) that parse it server-side.
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
 *
 * `.xlsx` support (batch posterior, owner brief "Excel upload capability"):
 * unlike `.csv`, an `.xlsx` file is NEVER parsed here -- SheetJS/`xlsx` is
 * the only JS library that reads real Excel binaries and its npm-published
 * build carries two unpatched HIGH advisories (ReDoS, prototype pollution)
 * with no fixed version ever published to npm. Instead, the raw file is
 * sent as `multipart/form-data` straight to the backend
 * (`validarCargaArchivo`/`subirCargaArchivo`), which parses it server-side
 * with `openpyxl` (`backend/app/motored/services/carga_excel.py`) using the
 * SAME column/alias config as `COLUMNAS_POR_ENTIDAD` below, then feeds the
 * result into the exact same `validate_rows`/`procesar_carga` pipeline as
 * the `.csv` path. Selecting an `.xlsx` file triggers an immediate dry-run
 * validate call -- there is no editable row-preview table for Excel (an
 * accepted UX difference from `.csv`); the existing `CargaResultPanel`
 * below doubles as that preview.
 */
import { useState } from 'react';
import Papa from 'papaparse';
import { validarCarga, subirCarga, validarCargaArchivo, subirCargaArchivo } from '../../../lib/motored/api';
import InfoTooltip from '../InfoTooltip';

// Columnas esperadas por maestro (sucursal/bodega/proveedor/referencia).
// `aliases` es case/acento-insensible: cubre variantes razonables del
// encabezado tal como puede venir de Excel.
const COLUMNAS_POR_ENTIDAD = {
  sucursal: [
    { key: 'nombre', label: 'Nombre', required: true, aliases: ['nombre', 'sucursal'] },
    {
      key: 'sic', label: 'SIC', required: false, aliases: ['sic'],
      help: 'Código con el que el proveedor (HMCL) identifica esta sucursal en sus sistemas.',
    },
    {
      key: 'dias_seguridad', label: 'Días de seguridad', required: false,
      aliases: ['dias_seguridad', 'dias seguridad', 'días de seguridad', 'días seguridad'],
      help: 'Colchón de días extra sobre el tiempo normal de reposición, para cubrir imprevistos. Por defecto 2.5 días.',
    },
    {
      key: 'dias_empaque', label: 'Días de empaque', required: false,
      aliases: ['dias_empaque', 'dias empaque', 'días de empaque', 'días empaque'],
      help: 'Días propios de ESTA sucursal para armar un pedido. Si lo dejás vacío, se usa el valor por defecto del proveedor.',
    },
    {
      key: 'dias_transito', label: 'Días de tránsito', required: false,
      aliases: ['dias_transito', 'dias transito', 'días de tránsito', 'días tránsito'],
      help: 'Días propios de ESTA sucursal para que le llegue un pedido. Si lo dejás vacío, se usa el valor por defecto del proveedor.',
    },
    {
      key: 'bodega_principal', label: 'Bodega principal', required: false,
      aliases: ['bodega_principal', 'bodega principal'],
      help: 'Código de la bodega principal de esta sucursal (ej: BE051).',
    },
    {
      key: 'departamento', label: 'Departamento', required: false, aliases: ['departamento'],
    },
    {
      key: 'ciudad', label: 'Ciudad', required: false, aliases: ['ciudad'],
    },
    {
      key: 'fecha_apertura', label: 'Fecha de apertura', required: false,
      aliases: ['fecha_apertura', 'fecha apertura'],
      help: 'Fecha en que la sucursal abrió operaciones. Se usa más adelante para no contar meses en los que todavía no existía.',
    },
  ],
  // Nota de alcance: la sucursal de cada bodega NO se asigna por CSV en
  // esta carga masiva (el back-end espera el `id` real de la sucursal, no
  // su nombre, y esa resolución nombre->id todavía no existe para bodegas
  // como sí existe para `proveedor_codigo` en `referencia`). Se asigna
  // editando la bodega individualmente después de cargarla.
  // `bodega_principal` (consolidación, spec §5.2) NO se expone acá a
  // propósito (owner request, 2026-09-16) -- sin uso en Fase 1, la columna
  // de la base de datos sigue existiendo para cuando la Fase 2 la necesite.
  bodega: [
    { key: 'codigo', label: 'Código', required: true, aliases: ['codigo', 'código', 'bodega'] },
    { key: 'descripcion', label: 'Descripción', required: false, aliases: ['descripcion', 'descripción'] },
  ],
  proveedor: [
    { key: 'codigo', label: 'Código', required: true, aliases: ['codigo', 'código', 'proveedor'] },
    { key: 'nombre', label: 'Nombre', required: true, aliases: ['nombre'] },
    {
      key: 'es_principal', label: 'Principal (Sí/No)', required: false, type: 'boolean',
      aliases: ['es_principal', 'principal', 'principal (si/no)', 'principal (sí/no)'],
      help: 'Escribí "Sí" únicamente para HMCL, el proveedor principal. Dejalo vacío o "No" para el resto.',
    },
    {
      key: 'dias_seguridad_default', label: 'Días de seguridad (por defecto)', required: false,
      aliases: ['dias_seguridad_default', 'dias seguridad default', 'días de seguridad (por defecto)'],
      help: 'Colchón de días extra que se usa cuando una sucursal no tiene su propio valor cargado. Por defecto 2.5 días.',
    },
  ],
  // `proveedor_codigo` (no el id) -- el router del backend resuelve ese
  // código al id real del proveedor antes de escribir, así que acá alcanza
  // con el código tal cual aparece en la pestaña de Proveedores.
  referencia: [
    { key: 'codigo', label: 'Código', required: true, aliases: ['codigo', 'código', 'referencia'] },
    {
      key: 'proveedor_codigo', label: 'Código del proveedor', required: true,
      aliases: ['proveedor_codigo', 'codigo proveedor', 'código proveedor', 'proveedor'],
      help: 'El código del proveedor tal como aparece en la pestaña de Proveedores (ej: HMCL).',
    },
    { key: 'nombre', label: 'Nombre', required: false, aliases: ['nombre'] },
    {
      key: 'linea_comercial', label: 'Línea comercial', required: false,
      aliases: ['linea_comercial', 'línea comercial'],
      help: 'Ej: REPUESTOS, ACCESORIOS. No es una lista cerrada, se escribe como texto libre.',
    },
    {
      key: 'unidad_empaque', label: 'Unidad de empaque', required: false,
      aliases: ['unidad_empaque', 'unidad de empaque'],
      help: 'Cuántas unidades vienen por paquete. Nunca 0 — si viene vacío o en 0, el sistema lo corrige a 1 automáticamente.',
    },
    {
      key: 'precio_normal', label: 'Precio normal', required: false, aliases: ['precio_normal', 'precio normal'],
      help: 'El precio que usa el sistema para calcular el valor de los pedidos.',
    },
  ],
};

function toBoolean(value) {
  const v = String(value).trim().toLowerCase();
  return ['si', 'sí', 'true', '1', 'yes', 'x'].includes(v);
}

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
  const spec = COLUMNAS_POR_ENTIDAD[entidad] || [];
  const typeByKey = Object.fromEntries(spec.map((col) => [col.key, col.type]));
  const columnMap = buildColumnMap(entidad, rawHeaders);
  return parsedRows.map((row) => {
    const canonical = {};
    Object.entries(row).forEach(([rawHeader, value]) => {
      const key = columnMap[rawHeader];
      if (!key) return;
      const trimmed = typeof value === 'string' ? value.trim() : value;
      canonical[key] = typeByKey[key] === 'boolean' ? toBoolean(trimmed) : trimmed;
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

function isExcelFile(file) {
  return /\.xlsx$/i.test(file?.name || '');
}

function isPayloadEmpty(payload) {
  return Array.isArray(payload) ? payload.length === 0 : !payload;
}

// Shared by both the CSV path (`payload` = filas: array) and the Excel path
// (`payload` = file: File) -- `apiFn(entidad, payload)` is the only thing
// that differs between validar/subir x csv/xlsx, so one function handles
// all four combinations instead of two near-identical closures per mode.
async function submitCarga(apiFn, entidad, payload, { onSuccess, notifyOnSuccess, setLoading, setResultado }) {
  if (isPayloadEmpty(payload)) return;
  setLoading(true);
  setResultado(null);
  try {
    const res = await apiFn(entidad, payload);
    setResultado(res);
    if (notifyOnSuccess && res.ok) onSuccess?.(res);
  } catch (err) {
    setResultado({ ok: false, errores: [{ fila: 0, motivo: err.message }] });
  } finally {
    setLoading(false);
  }
}

function parseCsvFile(entidad, file, { setFilas, setParseError }) {
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
}

function useCargaMasiva(entidad, onSuccess) {
  const [fileName, setFileName] = useState('');
  const [filas, setFilas] = useState([]);
  const [excelFile, setExcelFile] = useState(null);
  const [isExcel, setIsExcel] = useState(false);
  const [parseError, setParseError] = useState('');
  const [resultado, setResultado] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleFile = (file) => {
    setResultado(null);
    setParseError('');
    setFilas([]);
    setExcelFile(null);
    setIsExcel(false);
    if (!file) return;
    setFileName(file.name);

    if (isExcelFile(file)) {
      // No client-side parsing at all for .xlsx -- the file goes straight
      // to the backend, and an immediate dry-run validate doubles as the
      // "preview" this format doesn't otherwise have.
      setIsExcel(true);
      setExcelFile(file);
      submitCarga(validarCargaArchivo, entidad, file, { setLoading, setResultado });
      return;
    }

    parseCsvFile(entidad, file, { setFilas, setParseError });
  };

  return {
    fileName, filas, isExcel, parseError, resultado, loading, handleFile,
    canSubmit: isExcel ? Boolean(excelFile) : filas.length > 0,
    runValidar: () => submitCarga(
      isExcel ? validarCargaArchivo : validarCarga,
      entidad,
      isExcel ? excelFile : filas,
      { setLoading, setResultado },
    ),
    runCarga: () => submitCarga(
      isExcel ? subirCargaArchivo : subirCarga,
      entidad,
      isExcel ? excelFile : filas,
      { onSuccess, notifyOnSuccess: true, setLoading, setResultado },
    ),
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
            {col.help && <InfoTooltip text={col.help} />}
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
        {fileName || 'Hacé clic acá para elegir el archivo (CSV o Excel .xlsx)'}
      </span>
      <span style={{ fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        En Excel: Archivo → Guardar como → tipo &quot;CSV (delimitado por comas)&quot;, o subí
        directamente el archivo .xlsx.
      </span>
      <input
        type="file"
        accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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
  const { fileName, filas, isExcel, canSubmit, parseError, resultado, loading, handleFile, runValidar, runCarga } =
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

        {isExcel && (
          <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
            Los archivos .xlsx se validan directamente en el servidor: no hay tabla editable por
            fila, solo el resultado de la validación del archivo completo (abajo).
          </p>
        )}

        {parseError && (
          <p style={{ margin: 0, color: 'var(--motored-danger, #c0392b)', fontSize: '0.75rem' }}>{parseError}</p>
        )}

        <FilasPreview filas={filas} />

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button type="button" className="motored-btn motored-btn-secondary" onClick={runValidar} disabled={loading || !canSubmit}>
            {loading ? 'Validando...' : 'Validar'}
          </button>
          <button type="button" className="motored-btn motored-btn-primary" onClick={runCarga} disabled={loading || !canSubmit}>
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
