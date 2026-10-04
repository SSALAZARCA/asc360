import { Gauge, KpiMiniGrid } from '../charts';
import { millones } from '../format';
import { periodoCorto } from '../periodo';
import InfoTooltip from '../../InfoTooltip';
import { COLOR } from '../tokens';
import { hayPresupuesto, miniKpis } from './datos';
import SinPresupuesto from './SinPresupuesto';
import { ROTULO, TARJETA } from './estilos';

function TarjetaGauge({ data }) {
  const red = data.cumplimiento.red;
  const conPresupuesto = hayPresupuesto(data);
  return (
    <section aria-label="Cumplimiento presupuesto" style={{ ...TARJETA, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <h2 style={{ ...ROTULO, alignSelf: 'flex-start' }}>Cumplimiento presupuesto · {periodoCorto(data.meses)}</h2>
      {conPresupuesto ? (
        <Gauge
          value={red.cumplimiento_pct} cortes={data.reglas.semaforo} maxWidth={240}
          label={`${millones(red.venta_cumplimiento)} de ${millones(red.presupuesto)}`}
        />
      ) : <SinPresupuesto />}
    </section>
  );
}

export function EtiquetaConTip({ label, tip }) {
  return <>{label}{tip && <> <InfoTooltip text={tip} /></>}</>;
}

function TarjetaIndicadores({ data }) {
  const items = miniKpis(data).map((k) => ({ ...k, label: <EtiquetaConTip label={k.label} tip={k.tip} />, key: k.label }));
  return (
    <section aria-label="Indicadores de la red" style={{ ...TARJETA, color: COLOR.ink }}>
      <KpiMiniGrid items={items} />
    </section>
  );
}

/** Top row: the compliance gauge and the six network figures. */
export default function CumplimientoTop({ data }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 16 }}>
      <TarjetaGauge data={data} />
      <TarjetaIndicadores data={data} />
    </div>
  );
}
