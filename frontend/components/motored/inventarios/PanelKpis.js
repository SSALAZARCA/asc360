/**
 * The five KPI cards of the live panel (WU12), built only from what the API
 * gives: the snapshot size (no counted-referencias figure yet), the
 * critical and reconteo counts, the partial net difference, and the pairs.
 * Accuracy is computed at close, so the live card shows "—".
 */
import InfoTooltip from '../InfoTooltip';
import { formatEntero, formatPesos, formatPesosConSigno, haceCuanto } from './conteosFormato';
import { kpiValorStyle, mutedStyle } from './estilos';
import { AYUDA_CRITICA, AYUDA_EXACTITUD, AYUDA_RECONTEO } from './ayudas';

const tarjeta = (alerta) => ({
  background: alerta ? 'var(--motored-danger-bg, #fdecea)' : 'var(--motored-surface, #ffffff)',
  border: `1px solid ${alerta ? 'var(--motored-danger, #c0392b)' : 'var(--motored-border, #e4e4e7)'}`,
  borderRadius: '12px', padding: '1rem 1.1rem', display: 'flex', flexDirection: 'column', gap: '0.35rem', minWidth: 0,
  color: alerta ? 'var(--motored-danger, #c0392b)' : undefined,
});

function Kpi({ titulo, ayuda, valor, detalle, alerta = false }) {
  return (
    <div style={tarjeta(alerta)}>
      <div style={{ fontSize: '0.8rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
        {titulo}{ayuda && <InfoTooltip text={ayuda} />}
      </div>
      <div style={kpiValorStyle}>{valor}</div>
      <div style={{ ...mutedStyle, color: alerta ? 'inherit' : mutedStyle.color }}>{detalle}</div>
    </div>
  );
}

function resumenReconteos(items) {
  const estados = items.map((f) => f.reconteo?.estado).filter(Boolean);
  const asignadas = estados.filter((e) => e === 'ASIGNADO').length;
  const recontadas = estados.filter((e) => e === 'TERMINADO').length;
  return `${asignadas} asignadas · ${recontadas} recontadas`;
}

function netaParcial(items) {
  return items.reduce((suma, f) => (f.valor == null ? suma : suma + Number(f.valor)), 0);
}

function ultimaActividad(sesiones) {
  const marcas = sesiones.map((s) => s.ultima_actividad_en).filter(Boolean).sort();
  return marcas.length ? `última actividad ${haceCuanto(marcas[marcas.length - 1])}` : 'sin actividad todavía';
}

export default function PanelKpis({ conteo, diferencias, sesiones }) {
  const items = diferencias?.items ?? [];
  const conectadas = sesiones.filter((s) => s.estado === 'CONECTADA').length;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '0.75rem' }}>
      <Kpi titulo="Avance" valor={formatEntero(conteo.snapshot?.lineas)} detalle="referencias en la foto del inventario" />
      <Kpi
        titulo="Diferencias críticas" ayuda={AYUDA_CRITICA} alerta={(diferencias?.criticas ?? 0) > 0}
        valor={formatEntero(diferencias?.criticas)} detalle={`desde ${formatPesos(conteo.umbrales?.critico)} cada una`}
      />
      <Kpi titulo="En reconteo" ayuda={AYUDA_RECONTEO} valor={formatEntero(diferencias?.en_reconteo)} detalle={resumenReconteos(items)} />
      <Kpi
        titulo="Exactitud parcial" ayuda={AYUDA_EXACTITUD} valor="—"
        detalle={`Diferencia neta${diferencias?.parcial ? ' parcial' : ''}: ${formatPesosConSigno(netaParcial(items))}`}
      />
      <Kpi titulo="Parejas activas" valor={formatEntero(conectadas)} detalle={ultimaActividad(sesiones)} />
    </div>
  );
}
