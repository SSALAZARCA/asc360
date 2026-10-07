'use client';
/**
 * "Referencias sin línea" of a raw ERP VENTAS carga, sorted by valor. With
 * `puedeAsignar` (ADMIN, COMPRAS) each row has a checkbox, a line select and
 * "Asignar"; above the table, "Seleccionar todas" and one select + button
 * assign a line to every checked row in one bulk request. Other roles read
 * "Sin línea". Every <option> has an explicit colour (dark theme).
 */
import { useState } from 'react';
import { numeroLegible, ordenarSinLinea, pesosLegibles } from './ventasErp';

const optionStyle = { color: '#1a1a18' };
const controlStyle = { minHeight: '44px', boxSizing: 'border-box', maxWidth: '100%' };
const checkStyle = { width: '24px', height: '24px', margin: '10px' };
const celdaStyle = { padding: '0.4rem 0.5rem', borderBottom: '1px solid var(--motored-border, #e4e4e7)', fontSize: '0.8rem' };
const numeroStyle = { ...celdaStyle, textAlign: 'right', whiteSpace: 'nowrap' };

function SelectLinea({ etiqueta, valor, lineas, onChange, disabled }) {
  return (
    <select aria-label={etiqueta} value={valor} style={{ ...controlStyle, width: '12rem' }} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
      <option value="" style={optionStyle}>Elegir línea...</option>
      {lineas.map((l) => <option key={l.valor} value={l.valor} style={optionStyle}>{l.etiqueta}</option>)}
    </select>
  );
}

function AsignacionMasiva({ cantidad, todas, lineas, ocupado, onTodas, onAsignar }) {
  const [linea, setLinea] = useState('');
  return (
    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
      <label style={{ display: 'flex', alignItems: 'center', fontSize: '0.8rem', cursor: 'pointer' }}>
        <input type="checkbox" aria-label="Seleccionar todas" checked={todas} style={checkStyle} onChange={(e) => onTodas(e.target.checked)} />
        Seleccionar todas
      </label>
      <span style={{ fontSize: '0.8rem' }}>{`${cantidad} ${cantidad === 1 ? 'seleccionada' : 'seleccionadas'}`}</span>
      <SelectLinea etiqueta="Línea para las seleccionadas" valor={linea} lineas={lineas} onChange={setLinea} disabled={ocupado} />
      <button
        type="button" className="motored-btn motored-btn-secondary" style={controlStyle}
        disabled={ocupado || !cantidad || !linea} onClick={() => onAsignar(linea)}
      >
        {ocupado ? 'Asignando...' : 'Asignar línea a seleccionadas'}
      </button>
    </div>
  );
}

function CeldaLinea({ referencia, lineas, ocupado, onAsignar }) {
  const [linea, setLinea] = useState('');
  return (
    <td style={celdaStyle}>
      <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
        <SelectLinea etiqueta={`Línea de ${referencia.codigo}`} valor={linea} lineas={lineas} onChange={setLinea} disabled={ocupado} />
        <button
          type="button" aria-label={`Asignar línea a ${referencia.codigo}`} className="motored-btn motored-btn-primary"
          style={controlStyle} disabled={ocupado || !linea} onClick={() => onAsignar(referencia.referencia_id, linea)}
        >
          Asignar
        </button>
      </div>
    </td>
  );
}

function Fila({ referencia, asignacion }) {
  const { puedeAsignar, seleccion, alternar } = asignacion;
  return (
    <tr>
      {puedeAsignar && (
        <td style={celdaStyle}>
          <input
            type="checkbox" aria-label={`Seleccionar ${referencia.codigo}`} style={checkStyle}
            checked={seleccion.includes(referencia.referencia_id)} onChange={() => alternar(referencia.referencia_id)}
          />
        </td>
      )}
      <td style={{ ...celdaStyle, whiteSpace: 'nowrap' }} className="motored-mono">{referencia.codigo}</td>
      <td style={celdaStyle}>{referencia.nombre}</td>
      <td style={numeroStyle}>{numeroLegible(referencia.filas)}</td>
      <td style={numeroStyle}>{numeroLegible(referencia.unidades)}</td>
      <td style={numeroStyle}>{pesosLegibles(referencia.valor)}</td>
      {puedeAsignar
        ? <CeldaLinea referencia={referencia} {...asignacion} />
        : <td style={{ ...celdaStyle, color: 'var(--motored-text-muted, #5a5a5a)' }}>Sin línea</td>}
    </tr>
  );
}

function Encabezado({ puedeAsignar }) {
  const columnas = ['Código', 'Nombre', 'Filas', 'Unidades', 'Valor (COP)', 'Línea'];
  return (
    <thead>
      <tr>
        {puedeAsignar && <th aria-label="Seleccionar" style={celdaStyle} />}
        {columnas.map((c) => <th key={c} style={{ ...celdaStyle, textAlign: 'left' }}>{c}</th>)}
      </tr>
    </thead>
  );
}

function useSeleccion(filas) {
  const [marcadas, setMarcadas] = useState([]);
  const ids = filas.map((f) => f.referencia_id);
  const seleccion = marcadas.filter((id) => ids.includes(id));
  const alternar = (id) => setMarcadas(seleccion.includes(id) ? seleccion.filter((x) => x !== id) : [...seleccion, id]);
  const todas = ids.length > 0 && seleccion.length === ids.length;
  return { seleccion, alternar, todas, marcarTodas: (si) => setMarcadas(si ? ids : []), limpiar: () => setMarcadas([]) };
}

export default function TablaSinLinea({ filas, puedeAsignar, lineas, ocupado, asignarUna, asignarVarias }) {
  const ordenadas = ordenarSinLinea(filas);
  const { seleccion, alternar, todas, marcarTodas, limpiar } = useSeleccion(ordenadas);
  const asignarSeleccionadas = async (linea) => {
    const elegidas = ordenadas.filter((f) => seleccion.includes(f.referencia_id));
    const ok = await asignarVarias(elegidas.map((f) => ({ referencia_id: f.referencia_id, linea_comercial: linea })));
    if (ok) limpiar();
  };
  const asignacion = { puedeAsignar, seleccion, alternar, lineas, ocupado, onAsignar: asignarUna };
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      {puedeAsignar && (
        <AsignacionMasiva
          cantidad={seleccion.length} todas={todas} lineas={lineas} ocupado={ocupado}
          onTodas={marcarTodas} onAsignar={asignarSeleccionadas}
        />
      )}
      <div style={{ overflowX: 'auto', maxWidth: '100%' }}>
        <table aria-label="Referencias sin línea" style={{ width: '100%', borderCollapse: 'collapse', minWidth: '640px' }}>
          <Encabezado puedeAsignar={puedeAsignar} />
          <tbody>
            {ordenadas.map((r) => <Fila key={r.referencia_id} referencia={r} asignacion={asignacion} />)}
          </tbody>
        </table>
      </div>
    </div>
  );
}
