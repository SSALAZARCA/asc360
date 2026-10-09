/**
 * The five KPI cards of the live panel (prototype "Main", WU12/WU12b): the
 * real progress (counted / universe referencias, with its bar), the
 * critical and reconteo counts, the partial accuracy over what is counted
 * so far with its net difference, and the active pairs with the last
 * reading. `vivo` is the `/panel` answer; `diferencias` the full table.
 */
import InfoTooltip from '../InfoTooltip';
import {
  formatEntero, formatPesos, formatPesosConSigno, formatPorcentaje, haceCuanto, porcentajeAvance,
} from './conteosFormato';
import { kpiValorStyle, mutedStyle } from './estilos';
import { AYUDA_AVANCE, AYUDA_CRITICA, AYUDA_EXACTITUD, AYUDA_RECONTEO } from './ayudas';

const tarjeta = (alerta) => ({
  background: alerta ? 'var(--motored-danger-bg, #fdecea)' : 'var(--motored-surface, #ffffff)',
  border: `1px solid ${alerta ? 'var(--motored-danger, #c0392b)' : 'var(--motored-border, #e4e4e7)'}`,
  borderRadius: '12px', padding: '1rem 1.1rem', display: 'flex', flexDirection: 'column', gap: '0.35rem', minWidth: 0,
  color: alerta ? 'var(--motored-danger, #c0392b)' : undefined,
});

function Kpi({ titulo, ayuda, valor, detalle, alerta = false, children }) {
  return (
    <div style={tarjeta(alerta)}>
      <div style={{ fontSize: '0.8rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
        {titulo}{ayuda && <InfoTooltip text={ayuda} />}
      </div>
      <div style={kpiValorStyle}>{valor}</div>
      {children}
      <div style={{ ...mutedStyle, color: alerta ? 'inherit' : mutedStyle.color }}>{detalle}</div>
    </div>
  );
}

function Barra({ pct }) {
  return (
    <div
      role="progressbar" aria-label="Avance del conteo" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct ?? 0}
      style={{ height: '8px', borderRadius: '999px', background: 'var(--motored-surface-alt, #f4f4f5)', overflow: 'hidden' }}
    >
      <div style={{ width: `${pct ?? 0}%`, height: '100%', background: 'var(--motored-brand, #e20714)' }} />
    </div>
  );
}

function resumenReconteos(items) {
  const estados = items.map((f) => f.reconteo?.estado).filter(Boolean);
  const asignadas = estados.filter((e) => e === 'ASIGNADO').length;
  const recontadas = estados.filter((e) => e === 'TERMINADO').length;
  return `${asignadas} asignadas · ${recontadas} recontadas`;
}

function avanceTexto(progreso) {
  if (!progreso) return '—';
  return `${formatEntero(progreso.refs_contadas)} / ${formatEntero(progreso.refs_universo)}`;
}

function ultimaLectura(progreso) {
  const ultima = progreso?.ultima_lectura_en;
  return ultima ? `última lectura ${haceCuanto(ultima)}` : 'sin lecturas todavía';
}

export default function PanelKpis({ conteo, vivo, diferencias, sesiones }) {
  const items = diferencias?.items ?? [];
  const resumen = vivo?.diferencias_resumen ?? diferencias;
  const exactitud = vivo?.exactitud_parcial;
  const conectadas = sesiones.filter((s) => s.estado === 'CONECTADA').length;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '0.75rem' }}>
      <Kpi titulo="Avance" ayuda={AYUDA_AVANCE} valor={avanceTexto(vivo?.progreso)} detalle="referencias contadas">
        <Barra pct={porcentajeAvance(vivo?.progreso)} />
      </Kpi>
      <Kpi
        titulo="Diferencias críticas" ayuda={AYUDA_CRITICA} alerta={(resumen?.criticas ?? 0) > 0}
        valor={formatEntero(resumen?.criticas)} detalle={`desde ${formatPesos(conteo.umbrales?.critico)} cada una`}
      />
      <Kpi titulo="En reconteo" ayuda={AYUDA_RECONTEO} valor={formatEntero(resumen?.en_reconteo)} detalle={resumenReconteos(items)} />
      <Kpi
        titulo="Exactitud parcial" ayuda={AYUDA_EXACTITUD} valor={formatPorcentaje(exactitud?.exactitud_pct)}
        detalle={exactitud
          ? `Diferencia neta parcial: ${formatPesosConSigno(exactitud.valor_diferencia_neta)}`
          : 'Sin referencias contadas todavía'}
      />
      <Kpi titulo="Parejas activas" valor={formatEntero(conectadas)} detalle={ultimaLectura(vivo?.progreso)} />
    </div>
  );
}
