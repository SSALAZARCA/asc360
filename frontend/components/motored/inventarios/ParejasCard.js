/**
 * "Parejas" (WU12/WU12b): each pair with its current location, its live
 * readings (from `/panel`), its reconteo tasks (from the differences) and
 * its last sign of life (reading or request), and "Desconectar". For the
 * leader, a connected pair silent for more than MINUTOS_SIN_ACTIVIDAD
 * shows in yellow ("Sin actividad hace N min"): it may hold readings it
 * has not sent.
 */
import { formatEntero, haceCuanto, minutosSinActividad, ultimaSenal } from './conteosFormato';
import { cardStyle, h2Style, mutedStyle } from './estilos';

function tareas(sesionId, items) {
  const propias = items.filter((f) => f.reconteo?.sesion?.id === sesionId);
  if (propias.length === 0) return null;
  const hechas = propias.filter((f) => f.reconteo.estado === 'TERMINADO').length;
  return `Reconteos: ${hechas} de ${propias.length}`;
}

function Pareja({ sesion, items, opera, ahora, onDesconectar }) {
  const conectada = sesion.estado === 'CONECTADA';
  const inactiva = opera ? minutosSinActividad(sesion, ahora) : null;
  const reconteos = tareas(sesion.id, items);
  const detalle = [
    sesion.ubicacion_actual?.nombre ?? 'Sin ubicación',
    sesion.lecturas == null ? null : `${formatEntero(sesion.lecturas)} lecturas`,
    conectada ? haceCuanto(ultimaSenal(sesion), ahora) : 'Desconectada',
  ].filter(Boolean).join(' · ');
  return (
    <div
      data-inactiva={inactiva != null ? 'si' : undefined}
      style={{
        display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.6rem 0.75rem', borderRadius: '10px',
        border: `1px solid ${inactiva != null ? 'var(--motored-warning, #d97706)' : 'var(--motored-border, #e4e4e7)'}`,
        background: inactiva != null ? 'var(--motored-warning-bg, #fef3e2)' : undefined,
        opacity: conectada ? 1 : 0.6,
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 700, fontSize: '0.875rem' }}>{sesion.etiqueta}</div>
        <div style={{ ...mutedStyle, fontSize: '0.75rem' }}>{detalle}</div>
        {inactiva != null && (
          <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--motored-data-mid-ink, #8a4104)' }}>
            Sin actividad hace {inactiva} min
          </div>
        )}
        {reconteos && <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--motored-data-mid-ink, #8a4104)' }}>{reconteos}</div>}
      </div>
      {opera && conectada && (
        <button
          type="button" className="motored-btn motored-btn-secondary" style={{ minHeight: '44px' }}
          aria-label={`Desconectar ${sesion.etiqueta.split(' · ')[0]}`} onClick={() => onDesconectar(sesion)}
        >
          Desconectar
        </button>
      )}
    </div>
  );
}

export default function ParejasCard({ sesiones, items, opera, onDesconectar, ahora = Date.now() }) {
  const conectadas = sesiones.filter((s) => s.estado === 'CONECTADA').length;
  const orden = [...sesiones].sort((a, b) => (a.estado === 'CONECTADA' ? 0 : 1) - (b.estado === 'CONECTADA' ? 0 : 1) || a.numero - b.numero);
  return (
    <div style={cardStyle}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h2 style={h2Style}>Parejas</h2>
        <span style={{ ...mutedStyle, fontSize: '0.8rem' }}>{conectadas} conectadas</span>
      </div>
      {orden.length === 0 && <p style={{ ...mutedStyle, margin: 0 }}>Todavía no entra ninguna pareja.</p>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
        {orden.map((s) => (
          <Pareja key={s.id} sesion={s} items={items} opera={opera} ahora={ahora} onDesconectar={onDesconectar} />
        ))}
      </div>
    </div>
  );
}
