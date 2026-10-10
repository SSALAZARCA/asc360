/**
 * "Parejas" (WU12/WU12b; owner decision 2026-10-10): each pair with the
 * units it counted (its non-voided readings, from `/panel`), sorted by
 * units with a bar relative to the leading pair, its reconteo tasks (from
 * the differences) and "Desconectar". For the leader, a connected pair
 * silent for more than MINUTOS_SIN_ACTIVIDAD shows in yellow ("Sin
 * actividad hace N min"): it may hold readings it has not sent.
 */
import { formatUnidades, minutosSinActividad, parejaCorta } from './conteosFormato';
import { cardStyle, h2Style, mutedStyle } from './estilos';

const unidadesDe = (sesion) => Number(sesion.unidades) || 0;

function tareas(sesionId, items) {
  const propias = items.filter((f) => f.reconteo?.sesion?.id === sesionId);
  if (propias.length === 0) return null;
  const hechas = propias.filter((f) => f.reconteo.estado === 'TERMINADO').length;
  return `Reconteos: ${hechas} de ${propias.length}`;
}

function BarraUnidades({ sesion, maximo }) {
  const pct = maximo > 0 ? Math.round((100 * unidadesDe(sesion)) / maximo) : 0;
  return (
    <div
      role="progressbar" aria-label={`Unidades de ${parejaCorta(sesion.etiqueta)}`}
      aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}
      style={{ flex: 1, minWidth: '40px', height: '6px', borderRadius: '999px', background: 'var(--motored-surface-alt, #f4f4f5)', overflow: 'hidden' }}
    >
      <div style={{ width: `${pct}%`, height: '100%', background: 'var(--motored-brand, #e20714)' }} />
    </div>
  );
}

function Pareja({ sesion, items, opera, ahora, maximo, onDesconectar }) {
  const conectada = sesion.estado === 'CONECTADA';
  const inactiva = opera ? minutosSinActividad(sesion, ahora) : null;
  const reconteos = tareas(sesion.id, items);
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.25rem' }}>
          <BarraUnidades sesion={sesion} maximo={maximo} />
          <span style={{ fontSize: '0.8rem', fontWeight: 700, whiteSpace: 'nowrap' }}>{formatUnidades(sesion.unidades)}</span>
        </div>
        {!conectada && <div style={{ ...mutedStyle, fontSize: '0.75rem' }}>Desconectada</div>}
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
  const orden = [...sesiones].sort((a, b) => unidadesDe(b) - unidadesDe(a) || a.numero - b.numero);
  const maximo = orden.length ? unidadesDe(orden[0]) : 0;
  return (
    <div style={cardStyle}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h2 style={h2Style}>Parejas</h2>
        <span style={{ ...mutedStyle, fontSize: '0.8rem' }}>{conectadas} conectadas</span>
      </div>
      {orden.length === 0 && <p style={{ ...mutedStyle, margin: 0 }}>Todavía no entra ninguna pareja.</p>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
        {orden.map((s) => (
          <Pareja key={s.id} sesion={s} items={items} opera={opera} ahora={ahora} maximo={maximo} onDesconectar={onDesconectar} />
        ))}
      </div>
    </div>
  );
}
