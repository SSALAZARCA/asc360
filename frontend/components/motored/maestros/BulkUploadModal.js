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
import { validarCarga, subirCarga, validarCargaArchivo, subirCargaArchivo, descargarPlantilla } from '../../../lib/motored/api';
import InfoTooltip from '../InfoTooltip';
import ReemplazoReferenciasResumen from './ReemplazoReferenciasResumen';

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
  // Los campos "_default" (dias_empaque/transito/seguridad_default) NO se
  // exponen acá a propósito (owner request, 2026-09-16) -- toda sucursal
  // siempre tiene su propio valor cargado hoy, así que el respaldo nunca
  // se usa en la práctica. Las columnas de la base de datos siguen
  // existiendo para cuando una fase futura las necesite.
  proveedor: [
    { key: 'codigo', label: 'Código', required: true, aliases: ['codigo', 'código', 'proveedor'] },
    { key: 'nombre', label: 'Nombre', required: true, aliases: ['nombre'] },
    {
      key: 'es_principal', label: 'Principal (Sí/No)', required: false, type: 'boolean',
      aliases: ['es_principal', 'principal', 'principal (si/no)', 'principal (sí/no)'],
      help: 'Escribí "Sí" únicamente para HMCL, el proveedor principal. Dejalo vacío o "No" para el resto.',
    },
  ],
  // Layout de negocio de 9 columnas, EN ESTE ORDEN (owner request
  // 2026-09-28) -- mismo orden/labels que `ALIASES_POR_ENTIDAD` en
  // `backend/app/motored/services/carga_excel.py` y que la tabla de
  // `ReferenciasTab.js`. La `label` siempre matchea sola (alias implícito en
  // `buildColumnMap`); `aliases` cubre los encabezados snake_case y las
  // labels de plantillas anteriores. `precio_venta` salió del layout (la
  // columna de la base de datos se conserva).
  referencia: [
    { key: 'codigo', label: 'Código', required: true, aliases: ['codigo', 'referencia'] },
    {
      key: 'proveedor_codigo', label: 'Código del proveedor', required: true,
      aliases: ['proveedor_codigo', 'codigo proveedor', 'codigo del proveedor', 'proveedor'],
      help: 'El código del proveedor tal como aparece en la pestaña de Proveedores (ej: HMCL). Identifica al proveedor, no es un número de parte.',
    },
    { key: 'nombre', label: 'Nombre', required: false, aliases: ['nombre'] },
    {
      key: 'linea_comercial', label: 'Línea comercial', required: false,
      aliases: ['linea_comercial', 'linea comercial'],
      help: 'Ej: REPUESTOS, ACCESORIOS. No es una lista cerrada, se escribe como texto libre.',
    },
    {
      key: 'unidad_empaque', label: 'Unidad de empaque', required: false,
      aliases: ['unidad_empaque', 'unidad de empaque'],
      help: 'Cuántas unidades vienen por paquete. Nunca 0 — si viene vacío o en 0, el sistema lo corrige a 1 automáticamente.',
    },
    {
      key: 'precio_normal', label: 'Precio Normal antes de IVA', required: false,
      aliases: ['precio_normal', 'precio normal'],
      help: 'Precio sin IVA. Es el precio que usa el sistema para calcular el valor de los pedidos.',
    },
    {
      key: 'precio_publico', label: 'Precio Público antes de IVA', required: false,
      aliases: ['precio_publico', 'precio publico', 'precio al publico'],
      help: 'Precio al público sin IVA. Informativo únicamente — no se usa para calcular el valor de los pedidos.',
    },
    {
      key: 'sustituida_por_codigo', label: 'Código de referencia sustituta', required: false,
      aliases: [
        'sustituida_por_codigo', 'sustituida por codigo', 'codigo sustituta',
        'codigo de referencia sustituta',
      ],
      help: 'Si esta referencia fue reemplazada por otra del MISMO proveedor (ya existente o cargada en este mismo archivo), poné acá el código de esa otra referencia. La referencia sustituta debe ser del mismo proveedor. Dejalo vacío si no aplica.',
    },
    {
      key: 'homologados', label: 'Homologados otras marcas', required: false,
      aliases: ['homologados', 'homologados otras marcas'],
      help: 'Modelos de moto de otras marcas con los que este repuesto es compatible. Podés poner varios en la misma celda, separados por coma o punto y coma (ej: Yamaha FZ 150; Honda CB 190R).',
    },
  ],
  // Maestro de vendedores: upsert por nombre normalizado, nunca borra a nadie.
  // Mismo orden/alias que `ALIASES_POR_ENTIDAD.vendedor` del backend. El usuario
  // enlazado NO va en el Excel (se elige a mano en la pantalla).
  vendedor: [
    {
      key: 'nombre', label: 'Nombre vendedor', required: true,
      aliases: ['nombre', 'nombre vendedor', 'vendedor', 'nombre del vendedor'],
      help: 'Tiene que ser igual al nombre que aparece en la columna Vendedor del archivo de ventas del ERP. Se compara sin tildes, sin mayúsculas y sin espacios de más.',
    },
    {
      key: 'cargo', label: 'Cargo', required: true, aliases: ['cargo'],
      help: 'Lo que hace la persona (ej: ASESOR DE REPUESTOS, JEFE DE TALLER, CAJERO POSVENTA). Es texto libre; se guarda en mayúsculas.',
    },
    {
      key: 'sucursal_nombre', label: 'Sucursal', required: false,
      aliases: ['sucursal', 'sucursal_nombre', 'sucursal principal'],
      help: 'Sucursal principal donde trabaja, con el nombre que ya tiene en la pestaña Sucursales. Si el nombre no existe, el archivo se rechaza.',
    },
    {
      key: 'cedula', label: 'Cédula', required: false,
      aliases: ['cedula', 'cédula', 'documento', 'identificacion'],
      help: 'Documento de identidad. Es opcional.',
    },
  ],
  // Lista de NIT de clientes Tecnired: cada carga REEMPLAZA la lista completa.
  // Mismo orden/alias que `ALIASES_POR_ENTIDAD.cliente_tecnired` del backend.
  cliente_tecnired: [
    {
      key: 'nit', label: 'NIT', required: true,
      aliases: ['nit', 'nit / cedula', 'nit/cedula', 'cliente factura', 'cedula', 'cédula'],
      help: 'NIT o cédula del cliente tal como sale en la factura (también sirve el encabezado "Cliente factura"). Se limpia solo: sin espacios y sin el punto del final.',
    },
    {
      key: 'razon_social', label: 'Razón social', required: false,
      aliases: ['razon_social', 'razon social', 'razón social', 'nombre'],
      help: 'Nombre del cliente. Es solo informativo, se puede dejar vacío.',
    },
  ],
};

// Nombre legible de cada entidad para el título del modal (las claves
// internas como `cliente_tecnired` no se le muestran al usuario).
const TITULO_POR_ENTIDAD = { cliente_tecnired: 'Clientes Tecnired', vendedor: 'Vendedores' };

// Entidades cuya carga reemplaza la lista completa en vez de actualizar fila por fila.
const ENTIDADES_DE_REEMPLAZO = ['cliente_tecnired'];

// `referencia` también reemplaza el maestro completo, pero con resumen previo y
// confirmación explícita (ver `ReemplazoReferenciasResumen`), no con el botón "Cargar".
const ENTIDAD_REEMPLAZO_CON_RESUMEN = 'referencia';

function toBoolean(value) {
  const v = String(value).trim().toLowerCase();
  return ['si', 'sí', 'true', '1', 'yes', 'x'].includes(v);
}

function normalizeHeader(header) {
  return header
    .normalize('NFD').replace(/[̀-ͯ]/g, '') // saca tildes
    .trim().toLowerCase();
}

// Indexes of every header matching `col` -- the label + aliases go through
// the same normalization as the header, so accented aliases/labels (e.g.
// "Línea comercial") also match.
function matchingHeaderIndexes(col, normalizedHeaders) {
  const aliases = [col.label, ...col.aliases].map(normalizeHeader);
  return normalizedHeaders.flatMap((h, idx) => (aliases.includes(h) ? [idx] : []));
}

function buildColumnMap(entidad, rawHeaders) {
  const spec = COLUMNAS_POR_ENTIDAD[entidad] || [];
  const normalizedHeaders = rawHeaders.map(normalizeHeader);
  const map = {}; // rawHeader -> canonicalKey
  spec.forEach((col) => {
    const [idx] = matchingHeaderIndexes(col, normalizedHeaders);
    if (idx !== undefined) map[rawHeaders[idx]] = col.key;
  });
  return map;
}

// Same rule as the backend (`carga_excel.py::ColumnaDuplicadaError`): two
// headers mapping to the SAME field are rejected, never silently ignored.
function duplicatedColumnsError(entidad, rawHeaders) {
  const spec = COLUMNAS_POR_ENTIDAD[entidad] || [];
  const normalizedHeaders = rawHeaders.map(normalizeHeader);
  const col = spec.find((c) => matchingHeaderIndexes(c, normalizedHeaders).length > 1);
  if (!col) return '';
  const encabezados = matchingHeaderIndexes(col, normalizedHeaders).map((idx) => `'${rawHeaders[idx].trim()}'`);
  return `La columna '${col.label}' aparece más de una vez en el archivo (${encabezados.join(', ')}). Dejá una sola.`;
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
      if (trimmed === '' || trimmed == null) {
        // Blank = "not provided" (the backend drops it); never coerce it,
        // e.g. a blank "Principal" must not become an explicit false.
        canonical[key] = '';
        return;
      }
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
async function submitCarga(apiFn, entidad, payload, { onSuccess, notifyOnSuccess, setLoading, setResultado, opciones }) {
  if (isPayloadEmpty(payload)) return;
  setLoading(true);
  setResultado(null);
  try {
    const res = await (opciones ? apiFn(entidad, payload, opciones) : apiFn(entidad, payload));
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
      const duplicadas = duplicatedColumnsError(entidad, rawHeaders);
      if (duplicadas) {
        setParseError(duplicadas);
        return;
      }
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

// Resumen del reemplazo de `referencia`: sale del último validar OK y se
// conserva si aplicar falla (p.ej. 409), para poder reintentar sin revalidar.
function useResumenReemplazo(resultado) {
  const [vigente, setVigente] = useState(null);
  const delResultado = resultado?.ok && resultado.resumen_reemplazo ? resultado.resumen_reemplazo : null;
  return { resumen: delResultado || vigente, delResultado, conservar: setVigente };
}

function useCargaMasiva(entidad, onSuccess) {
  const [fileName, setFileName] = useState('');
  const [filas, setFilas] = useState([]);
  const [excelFile, setExcelFile] = useState(null);
  const [isExcel, setIsExcel] = useState(false);
  const [parseError, setParseError] = useState('');
  const [resultado, setResultado] = useState(null);
  const [loading, setLoading] = useState(false);
  const { resumen, delResultado, conservar } = useResumenReemplazo(resultado);
  const enviar = (apiCsv, apiExcel, extra) => submitCarga(
    isExcel ? apiExcel : apiCsv,
    entidad,
    isExcel ? excelFile : filas,
    { setLoading, setResultado, ...extra },
  );

  const handleFile = (file) => {
    setResultado(null);
    conservar(null);
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

  const handleDescargarPlantilla = () => {
    setParseError('');
    descargarPlantilla(entidad).catch((err) => {
      setParseError(`No se pudo descargar la plantilla: ${err.message}`);
    });
  };

  const aplicar = (opciones) => {
    if (delResultado) conservar(delResultado);
    return enviar(subirCarga, subirCargaArchivo, { onSuccess, notifyOnSuccess: true, opciones });
  };

  return {
    fileName, filas, isExcel, parseError, resultado, loading, handleFile,
    resumenReemplazo: resumen, runConfirmarReemplazo: aplicar,
    canSubmit: isExcel ? Boolean(excelFile) : filas.length > 0,
    handleDescargarPlantilla,
    runValidar: () => {
      conservar(null);
      return enviar(validarCarga, validarCargaArchivo);
    },
    runCarga: () => enviar(subirCarga, subirCargaArchivo, { onSuccess, notifyOnSuccess: true }),
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

  if (resultado.ok && resultado.resumen_reemplazo) {
    return (
      <div style={{ color: 'var(--motored-success, #15803d)', fontSize: '0.8rem', fontWeight: 700 }}>
        Archivo válido — {resultado.total_filas} filas leídas. Revise el resumen de abajo antes de confirmar.
      </div>
    );
  }

  if (resultado.ok) {
    return (
      <div style={{ color: 'var(--motored-success, #15803d)', fontSize: '0.8rem', fontWeight: 700 }}>
        OK — {resultado.total_filas} filas procesadas
        {typeof resultado.insertados === 'number' && ` (${resultado.insertados} nuevas, ${resultado.actualizados} actualizadas)`}
        {resultado.eliminados > 0 && ` — se reemplazaron ${resultado.eliminados} registros anteriores`}
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

function AvisoReemplazoReferencias() {
  return (
    <p style={{ margin: 0, fontSize: '0.75rem', fontWeight: 700, color: 'var(--motored-warning, #d97706)' }}>
      Atención: esta carga reemplaza el maestro completo. Las referencias que no estén en el archivo se
      desactivan (no se borran) y una celda en blanco borra lo que tenía guardado. Primero se muestra un
      resumen y recién después de confirmarlo se aplica.
    </p>
  );
}

export default function BulkUploadModal({ entidad, onClose, onSuccess }) {
  const {
    fileName, filas, isExcel, canSubmit, parseError, resultado, loading,
    handleFile, handleDescargarPlantilla, runValidar, runCarga,
    resumenReemplazo, runConfirmarReemplazo,
  } = useCargaMasiva(entidad, onSuccess);
  const conResumen = entidad === ENTIDAD_REEMPLAZO_CON_RESUMEN;

  return (
    <div role="dialog" aria-label={`Carga masiva de ${TITULO_POR_ENTIDAD[entidad] || entidad}`} style={overlayStyle}>
      <div style={boxStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 800, color: 'var(--motored-text, #1a1a18)' }}>
            Carga masiva — {TITULO_POR_ENTIDAD[entidad] || entidad}
          </h2>
          <button type="button" className="motored-btn motored-btn-tertiary" onClick={handleDescargarPlantilla}>
            Descargar plantilla Excel
          </button>
        </div>

        <ColumnasEsperadas entidad={entidad} />

        <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          Todo-o-nada: si una sola fila del archivo es inválida, no se escribe nada.
        </p>

        {ENTIDADES_DE_REEMPLAZO.includes(entidad) && (
          <p style={{ margin: 0, fontSize: '0.75rem', fontWeight: 700, color: 'var(--motored-warning, #d97706)' }}>
            Atención: cada carga reemplaza la lista completa. Los registros que no estén en el archivo se borran.
          </p>
        )}

        {conResumen && <AvisoReemplazoReferencias />}

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
          {!conResumen && (
            <button type="button" className="motored-btn motored-btn-primary" onClick={runCarga} disabled={loading || !canSubmit}>
              {loading ? 'Cargando...' : 'Cargar'}
            </button>
          )}
          <button type="button" className="motored-btn motored-btn-tertiary" onClick={onClose} disabled={loading}>
            Cerrar
          </button>
        </div>

        <CargaResultPanel resultado={resultado} />

        {conResumen && (
          <ReemplazoReferenciasResumen
            resumen={resumenReemplazo} loading={loading} onConfirmar={runConfirmarReemplazo}
          />
        )}
      </div>
    </div>
  );
}
