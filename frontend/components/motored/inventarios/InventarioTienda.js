/**
 * The store's latest inventory carga and its age (`GET /conteos/sucursales`):
 * green when fresh, a warning when older than the configured hours, and a
 * warning when the store has none. Used by the schedule dialog and the
 * start screen.
 */
import { fechaBogota, fechaHoraBogota } from '../../../lib/motored/fechas';
import { formatEntero } from './conteosFormato';
import { avisoStyle } from './estilos';

export function inventarioViejo(sucursal) {
  const inv = sucursal?.inventario;
  if (!inv || sucursal.vigencia_horas == null) return false;
  return Number(inv.antiguedad_horas) > Number(sucursal.vigencia_horas);
}

export default function InventarioTienda({ sucursal }) {
  const inv = sucursal?.inventario;
  if (!inv) {
    return (
      <div style={avisoStyle('warning')}>
        Esta tienda no tiene inventario cargado. Cárguelo en Maestros antes de iniciar el conteo.
      </div>
    );
  }
  const horas = `hace ${formatEntero(inv.antiguedad_horas)} horas`;
  const cargado = inv.aplicado_en ? fechaHoraBogota(inv.aplicado_en) : fechaBogota(inv.fecha_corte);
  if (inventarioViejo(sucursal)) {
    return (
      <div style={avisoStyle('warning')}>
        <div>
          <strong>Inventario cargado {cargado} ({horas}).</strong>{' '}
          Tiene más de {sucursal.vigencia_horas} horas: cargue uno nuevo en Maestros antes de iniciar,
          o inicie de todos modos y quedará registrado.
        </div>
      </div>
    );
  }
  return (
    <div style={avisoStyle('success')}>
      <div>
        <strong>Inventario cargado {cargado}</strong>
        <div>Corte {fechaBogota(inv.fecha_corte)} · {horas}</div>
      </div>
    </div>
  );
}
