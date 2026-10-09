'use client';
import { tarjeta } from './ingresosEstilos';
import { AMBAR } from './trasladosEstilos';
import { PALETA, nivelPorDias } from './semaforo';

const etiqueta = { margin: 0, fontSize: '12px', fontWeight: 500, letterSpacing: '.04em', textTransform: 'uppercase', color: 'var(--motored-text-muted, #595954)' };
const valorStyle = { margin: '6px 0 0', fontSize: '30px', fontWeight: 700, fontVariantNumeric: 'tabular-nums', letterSpacing: '-.01em' };
const pie = { margin: '6px 0 0', fontSize: '12.5px', color: 'var(--motored-text-muted, #595954)' };

const AYUDA_RECIBIDOS = 'La tienda certificó que ya recibió el repuesto, pero el traslado sigue vivo en el ERP: falta recibirlo allá. Es lo primero que hay que resolver.';

/** `tinta` / `borde` / `fondo` / `pie` color the card (amber priority card, or the semáforo level of the oldest). */
function Kpi({ nombre, valor, pista, ayuda, color }) {
  const estilo = color ? { ...tarjeta, border: `2px solid ${color.borde}`, background: color.fondo } : tarjeta;
  return (
    <div role="group" aria-label={nombre} title={ayuda} style={estilo}>
      <p style={{ ...etiqueta, ...(color ? { color: color.tinta, fontWeight: 700 } : {}) }}>{nombre}</p>
      <p style={{ ...valorStyle, ...(color ? { color: color.tinta } : {}) }}>{valor}</p>
      <p style={{ ...pie, ...(color ? { color: color.pie || color.tinta } : {}) }}>{pista}</p>
    </div>
  );
}

function colorPorDias(dias) {
  const p = PALETA[nivelPorDias(dias)];
  return p && { borde: p.color, fondo: p.soft, tinta: p.ink };
}

export default function TrasladosKpis({ resumen, filtrado = false }) {
  const r = resumen || {};
  const viejo = r.mas_antiguo;
  return (
    <div role="group" aria-label="Indicadores" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '14px' }}>
      <Kpi nombre="Pendientes" valor={r.pendientes ?? 0} pista={`${filtrado ? 'Con los filtros aplicados' : 'Traslados vivos en el ERP'} · ${r.lineas ?? 0} líneas`} />
      <Kpi
        nombre="Recibidos sin cargar al ERP" valor={r.recibidos_sin_erp ?? 0} pista="La tienda certificó que llegó · prioridad"
        ayuda={AYUDA_RECIBIDOS} color={AMBAR}
      />
      <Kpi nombre="Sin confirmar" valor={r.sin_confirmar ?? 0} pista="La tienda que recibe no ha respondido" />
      <Kpi nombre="Aún no llegan" valor={r.aun_no_llegan ?? 0} pista="La tienda dice que no ha llegado" />
      <Kpi
        nombre="Más antiguo" valor={viejo ? `${viejo.dias} días` : '—'} pista={viejo ? `${viejo.documento} · ${viejo.tienda}` : 'Sin traslados'}
        color={viejo ? colorPorDias(viejo.dias) : null}
      />
    </div>
  );
}
