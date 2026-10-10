'use client';
/**
 * ADMIN schedules a total count (store, leader, date) or, with `conteo`,
 * reschedules a PROGRAMADO one (date and leader). The chosen store shows
 * the age of its latest inventory, so a stale one is seen before the day.
 * A new count may be marked "Es de prueba" (odd/tasks/motored-conteo-prueba.md;
 * the dialog is ADMIN-only); a test count cannot be converted later.
 */
import { useEffect, useState } from 'react';
import DialogoPedido from '../pedidos/DialogoPedido';
import {
  listarLideres, listarSucursalesConteo, programarConteo, reprogramarConteo,
} from '../../../lib/motored/conteosApi';
import InventarioTienda from './InventarioTienda';
import { labelStyle, optionStyle, selectStyle } from './estilos';
import { NOMBRE_ROL_LIDER } from './conteosFormato';

function useOpciones(reprogramando) {
  const [sucursales, setSucursales] = useState([]);
  const [lideres, setLideres] = useState([]);
  const [error, setError] = useState('');
  useEffect(() => {
    let vivo = true;
    Promise.all([reprogramando ? [] : listarSucursalesConteo(), listarLideres()])
      .then(([s, l]) => { if (vivo) { setSucursales(s); setLideres(l); } })
      .catch((err) => { if (vivo) setError(err.message || 'No se pudieron cargar las opciones.'); });
    return () => { vivo = false; };
  }, [reprogramando]);
  return { sucursales, lideres, error };
}

/** "Nombre · Rol", so ADMIN tells a leader from a parts coordinator. */
function etiquetaLider(lider) {
  const rol = NOMBRE_ROL_LIDER[lider.rol];
  return rol ? `${lider.nombre} · ${rol}` : lider.nombre;
}

function Campo({ etiqueta, children }) {
  return <label style={labelStyle}>{etiqueta}{children}</label>;
}

const casillaStyle = { width: '24px', height: '24px', margin: 0, flexShrink: 0 };

function CasillaPrueba({ marcada, onCambio }) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', minHeight: '44px', cursor: 'pointer' }}>
      <input type="checkbox" aria-label="Es de prueba" checked={marcada} onChange={(e) => onCambio(e.target.checked)} style={casillaStyle} />
      <span>
        <strong>Es de prueba</strong>
        <span style={{ display: 'block', fontSize: '0.8rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
          Solo lo ve el administrador, no bloquea un conteo real y se puede borrar.
        </span>
      </span>
    </label>
  );
}

export default function ProgramarConteoDialog({ conteo, onCancel, onListo }) {
  const reprogramando = Boolean(conteo);
  const opciones = useOpciones(reprogramando);
  const [sucursalId, setSucursalId] = useState('');
  const [liderId, setLiderId] = useState(conteo?.lider?.id ?? '');
  const [fecha, setFecha] = useState(conteo?.fecha_programada ?? '');
  const [esPrueba, setEsPrueba] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState('');
  const sucursal = opciones.sucursales.find((s) => s.id === sucursalId);
  const completo = liderId && fecha && (reprogramando || sucursalId);

  const confirmar = async () => {
    setOcupado(true);
    setError('');
    try {
      if (reprogramando) {
        await reprogramarConteo(conteo.id, { fecha_programada: fecha, lider_id: liderId });
      } else {
        await programarConteo({
          sucursal_id: sucursalId, lider_id: liderId, fecha_programada: fecha, es_prueba: esPrueba,
        });
      }
      onListo();
    } catch (err) {
      setError(err.message || 'No se pudo programar el conteo.');
      setOcupado(false);
    }
  };

  return (
    <DialogoPedido
      titulo={reprogramando ? `Reprogramar conteo · ${conteo.sucursal.nombre}` : 'Programar conteo total'}
      descripcion={<span>La tienda se cuenta cerrada. El líder asignado es el único que inicia, sigue y cierra este conteo.</span>}
      error={error || opciones.error} ocupado={ocupado} confirmarDeshabilitado={!completo}
      textoConfirmar={reprogramando ? 'Guardar' : 'Programar'} onConfirm={confirmar} onCancel={onCancel}
    >
      {!reprogramando && (
        <Campo etiqueta="Tienda">
          <select value={sucursalId} onChange={(e) => setSucursalId(e.target.value)} style={selectStyle}>
            <option value="" style={optionStyle}>Elija una tienda</option>
            {opciones.sucursales.map((s) => <option key={s.id} value={s.id} style={optionStyle}>{s.nombre}</option>)}
          </select>
        </Campo>
      )}
      {sucursal && <InventarioTienda sucursal={sucursal} />}
      <Campo etiqueta="Líder del conteo">
        <select value={liderId} onChange={(e) => setLiderId(e.target.value)} style={selectStyle}>
          <option value="" style={optionStyle}>Elija un líder</option>
          {opciones.lideres.map((l) => <option key={l.id} value={l.id} style={optionStyle}>{etiquetaLider(l)}</option>)}
        </select>
      </Campo>
      <Campo etiqueta="Fecha">
        <input type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} style={selectStyle} />
      </Campo>
      {!reprogramando && <CasillaPrueba marcada={esPrueba} onCambio={setEsPrueba} />}
    </DialogoPedido>
  );
}
