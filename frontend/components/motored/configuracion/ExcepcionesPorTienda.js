'use client';
/**
 * "Valor propio por tienda" of a key with a per-sucursal scope: one field per
 * tienda that already has its own value, and a picker to give another tienda
 * one. Every save goes through CampoConfiguracion with the tienda's id.
 */
import { useEffect, useState } from 'react';
import CampoConfiguracion from './CampoConfiguracion';
import { listMaestros } from '../../../lib/motored/api';
import { columnaStyle, controlStyle, filaStyle, mutedStyle, optionStyle, touchStyle } from './styles';

/** The spec of one tienda: its own value as the value in force. */
const comoTienda = (spec, sucursalId, fila) => ({
  ...spec,
  por_sucursal: [],
  efectivo_global: fila
    ? { valor: fila.valor, fuente: 'SUCURSAL', vigente_desde: fila.vigente_desde, parametro_id: fila.parametro_id }
    : { ...spec.efectivo_global, fuente: 'DEFAULT' },
  programados: spec.programados.filter((p) => p.sucursal_id === sucursalId),
});

function useTiendas() {
  const [tiendas, setTiendas] = useState([]);
  useEffect(() => {
    let vivo = true;
    listMaestros('sucursales')
      .then((filas) => vivo && setTiendas(filas.filter((t) => t.activa !== false)))
      .catch(() => vivo && setTiendas([]));
    return () => { vivo = false; };
  }, []);
  return tiendas;
}

function Selector({ tiendas, elegida, onElegir, onAgregar }) {
  return (
    <div style={filaStyle}>
      <select aria-label="Tienda" value={elegida} style={controlStyle} onChange={(e) => onElegir(e.target.value)}>
        <option value="" style={optionStyle}>Elegir tienda…</option>
        {tiendas.map((t) => <option key={t.id} value={t.id} style={optionStyle}>{t.nombre}</option>)}
      </select>
      <button
        type="button" className="motored-btn motored-btn-secondary" style={touchStyle}
        disabled={!elegida} onClick={onAgregar}
      >
        Agregar tienda
      </button>
    </div>
  );
}

export default function ExcepcionesPorTienda({ spec, ayuda, recargar, onGuardar }) {
  const tiendas = useTiendas();
  const [elegida, setElegida] = useState('');
  const [nueva, setNueva] = useState(null);
  const nombre = (id) => (tiendas.find((t) => t.id === id) || {}).nombre || `Tienda ${String(id).slice(0, 8)}`;
  const propias = spec.por_sucursal.map((f) => f.sucursal_id);
  const libres = tiendas.filter((t) => !propias.includes(t.id) && t.id !== nueva);
  const guardado = () => { setNueva(null); setElegida(''); recargar?.(); };
  const extra = onGuardar ? { onGuardar } : {};
  return (
    <div style={columnaStyle}>
      <h3 style={{ margin: 0, fontSize: '0.9rem' }}>Valor propio por tienda</h3>
      <p style={mutedStyle}>Una tienda con valor propio ignora el valor general de arriba.</p>
      {spec.por_sucursal.map((fila) => (
        <CampoConfiguracion
          key={fila.sucursal_id} spec={comoTienda(spec, fila.sucursal_id, fila)} sucursalId={fila.sucursal_id}
          etiqueta={nombre(fila.sucursal_id)} ayuda={ayuda} onGuardado={guardado} {...extra}
        />
      ))}
      {nueva && (
        <CampoConfiguracion
          key={nueva} spec={comoTienda(spec, nueva, null)} sucursalId={nueva}
          etiqueta={nombre(nueva)} ayuda={ayuda} onGuardado={guardado} {...extra}
        />
      )}
      <Selector
        tiendas={libres} elegida={elegida} onElegir={setElegida}
        onAgregar={() => { setNueva(elegida); setElegida(''); }}
      />
    </div>
  );
}
