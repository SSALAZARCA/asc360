'use client';
/** Corrida-level lifecycle buttons: close all drafts or the selected ones, send the selected, export the zip, recalculate failed tiendas. */
import { ACTION_ICONS } from '../actionIcons';
import { sinCantidad } from './acciones';

function Boton({ accion, texto, onClick, disabled = false, ayuda }) {
  const Icono = ACTION_ICONS[accion];
  return (
    <button
      type="button" className="motored-btn motored-btn-secondary" onClick={onClick} disabled={disabled} title={ayuda}
      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', minHeight: '44px' }}
    >
      {Icono && <Icono size={16} aria-hidden="true" />}
      {texto}
    </button>
  );
}

const todas = (lista, regla) => lista.length > 0 && lista.every(regla);

export default function AccionesCorrida({ corrida, seleccionadas, ocupado, onCerrar, onEnviar, onExportar, onRecalcular }) {
  if (corrida.es_escenario) return null;
  const tiendas = corrida.sucursales;
  const borradores = tiendas.filter((t) => t.acciones && t.acciones.cerrar);
  const fallidas = tiendas.filter((t) => t.estado === 'FALLIDA');
  const hayExportables = tiendas.some((t) => t.acciones && t.acciones.exportar);
  const n = seleccionadas.length;
  const sePuedeCerrar = todas(seleccionadas, (t) => t.acciones && t.acciones.cerrar);
  const sePuedeEnviar = todas(seleccionadas, (t) => t.acciones && t.acciones.enviar && !sinCantidad(t.unidades_a_pedir));
  if (borradores.length + fallidas.length === 0 && !hayExportables && n === 0) return null;
  return (
    <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'center' }}>
      {borradores.length > 0 && (
        <Boton accion="Cerrar" texto="Cerrar todas las listas" disabled={ocupado} onClick={() => onCerrar(borradores, true)} />
      )}
      {n > 0 && (
        <Boton
          accion="Cerrar" texto={`Cerrar seleccionadas (${n})`} disabled={ocupado || !sePuedeCerrar}
          ayuda={sePuedeCerrar ? undefined : 'Seleccione sólo tiendas en Borrador'} onClick={() => onCerrar(seleccionadas, false)}
        />
      )}
      {n > 0 && (
        <Boton
          accion="Marcar como enviado" texto={`Marcar seleccionadas como enviadas (${n})`} disabled={ocupado || !sePuedeEnviar}
          ayuda={sePuedeEnviar ? undefined : 'Seleccione sólo tiendas cerradas con algo que pedir'} onClick={() => onEnviar(seleccionadas)}
        />
      )}
      {hayExportables && <Boton accion="Exportar" texto="Exportar cerradas (.zip)" disabled={ocupado} onClick={onExportar} />}
      {fallidas.length > 0 && <Boton accion="Recalcular fallidas" texto="Recalcular fallidas" disabled={ocupado} onClick={() => onRecalcular(fallidas)} />}
    </div>
  );
}
