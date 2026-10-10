'use client';
/**
 * Start and access screen (prototype "Iniciar", WU11): 1. Tienda,
 * 2. Foto del inventario (age, staleness warning, "Iniciar conteo"),
 * 3. Acceso para las parejas (QR, code, link, print, rotate), 4. Pendientes
 * por sanear (before the start only, WU15), and the store's locations below. The store is fixed when the count is scheduled.
 */
import { fechaBogota } from '../../../lib/motored/fechas';
import { ESTADOS_ABIERTOS } from './conteosFormato';
import { cardStyle, filaFlexStyle, h2Style, mutedStyle, paginaStyle, tituloStyle } from './estilos';
import FotoInventario from './FotoInventario';
import PendientesPorSanear from './PendientesPorSanear';
import AccesoParejas from './AccesoParejas';
import UbicacionesPanel from './UbicacionesPanel';
import useUbicaciones from './useUbicaciones';
import VolverConteos from './VolverConteos';

export default function IniciarVista({ conteo, permisos, acceso, onIniciado, onVolverPanel }) {
  const abierto = ESTADOS_ABIERTOS.includes(conteo.estado);
  const ubicaciones = useUbicaciones(conteo.id);
  const tienda = conteo.sucursal.nombre;

  return (
    <section style={paginaStyle}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
        {abierto ? <VolverConteos texto="Volver al panel" onClick={onVolverPanel} /> : <VolverConteos />}
        <h1 style={tituloStyle}>{abierto ? `Conteo total · ${tienda}` : 'Nuevo conteo total'}</h1>
      </div>
      <div style={filaFlexStyle}>
        <div style={{ flex: '1 1 420px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={cardStyle}>
            <h2 style={h2Style}>1. Tienda</h2>
            <div style={{ fontSize: '1rem', fontWeight: 700 }}>{tienda}</div>
            <div style={mutedStyle}>
              Programado para el {fechaBogota(conteo.fecha_programada)} · Líder: {conteo.lider?.nombre ?? '—'}.
              Incluye todas las bodegas propias de la tienda.
            </div>
          </div>
          <FotoInventario conteo={conteo} permisos={permisos} onIniciado={onIniciado} />
          {conteo.estado === 'PROGRAMADO' && <PendientesPorSanear conteo={conteo} permisos={permisos} />}
        </div>
        <AccesoParejas
          conteo={conteo} permisos={permisos} acceso={acceso} ubicaciones={ubicaciones.lista}
        />
      </div>
      <UbicacionesPanel conteo={conteo} permisos={permisos} ubicaciones={ubicaciones} />
    </section>
  );
}
