'use client';
import { select, opcion, segmento, botonLink } from './ingresosEstilos';
import { PuntoNivel } from './SemaforoUi';
import { BANDAS_EDAD } from './semaforo';

export const ESTADOS_FILTRO = [
  [null, 'Todas'], ['LLEGO', 'Ya llegó sin ingresar'], ['SIN_CONFIRMAR', 'Sin confirmar'], ['NO_HA_LLEGADO', 'Aún no llega'],
];
// Age bands come from the semáforo thresholds; the API limits are inclusive on both ends.
export const EDADES = BANDAS_EDAD.map(([min, max, texto, nivel]) => [{ min, max }, texto, nivel]);
export const SIN_EDAD = EDADES[0][0];
export const FILTROS_VACIOS = { sucursal: '', estado: null, edad: SIN_EDAD };

function Segmentos({ nombre, opciones, valor, onElegir }) {
  return (
    <div role="group" aria-label={nombre} style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '12px', fontWeight: 500 }}>
      {nombre}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
        {opciones.map(([v, texto, nivel]) => (
          <button key={texto} type="button" aria-pressed={valor === v} style={segmento(valor === v)} onClick={() => onElegir(v)}>
            {nivel && <PuntoNivel nivel={nivel} />}{texto}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Tienda select, Estado and Antigüedad pills, and the "Filtros activos" line with its Limpiar button. */
export default function FiltrosIngresos({ filtros, tiendas, onCambiar, onLimpiar }) {
  const nombreTienda = tiendas.find((t) => t.sucursal_id === filtros.sucursal)?.tienda;
  const activos = [
    filtros.sucursal && (nombreTienda || 'Tienda'),
    filtros.estado && ESTADOS_FILTRO.find(([v]) => v === filtros.estado)?.[1],
    filtros.edad !== SIN_EDAD && EDADES.find(([v]) => v === filtros.edad)?.[1],
  ].filter(Boolean);
  return (
    <>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '14px 22px', alignItems: 'flex-end' }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '12px', fontWeight: 500 }}>
          Tienda
          <select style={select} value={filtros.sucursal} onChange={(e) => onCambiar('sucursal')(e.target.value)}>
            <option style={opcion} value="">Todas las tiendas</option>
            {tiendas.map((t) => (
              <option key={t.sucursal_id} style={opcion} value={t.sucursal_id}>{t.tienda}</option>
            ))}
          </select>
        </label>
        <Segmentos nombre="Estado" opciones={ESTADOS_FILTRO} valor={filtros.estado} onElegir={onCambiar('estado')} />
        <Segmentos nombre="Antigüedad" opciones={EDADES} valor={filtros.edad} onElegir={onCambiar('edad')} />
      </div>
      {activos.length > 0 && (
        <p style={{ margin: 0, fontSize: '13px', display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px' }}>
          <span>Filtros activos: {activos.join(' · ')}</span>
          <button type="button" style={botonLink} onClick={onLimpiar}>Limpiar</button>
        </p>
      )}
    </>
  );
}
