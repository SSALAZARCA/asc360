import { Gauge, KpiMiniGrid } from '../charts';
import { millones } from '../format';
import { periodoCorto } from '../periodo';
import InfoTooltip from '../../InfoTooltip';
import { COLOR } from '../tokens';
import VentaPorGrupo from './VentaPorGrupo';
import { hayPresupuesto, miniKpis } from './datos';
import SinPresupuesto from './SinPresupuesto';
import { ROTULO, TARJETA } from './estilos';

const TIP_GAUGE = 'Venta total de la compañía (todas las ventas) contra la suma de los presupuestos de los asesores en los meses con presupuesto.';

function TarjetaGauge({ data }) {
  const compania = data.cumplimiento.compania;
  const conPresupuesto = hayPresupuesto(data);
  return (
    <section aria-label="Cumplimiento presupuesto compañía" style={{ ...TARJETA, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <div style={{ alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: 6 }}>
        <h2 style={ROTULO}>Cumplimiento presupuesto compañía · {periodoCorto(data.meses)}</h2>
        <InfoTooltip text={TIP_GAUGE} />
      </div>
      {conPresupuesto ? (
        <>
          <Gauge
            value={compania.pct} cortes={data.reglas.semaforo} maxWidth={240}
            label={`${millones(compania.venta)} de ${millones(compania.presupuesto)}`}
          />
          <VentaPorGrupo compania={compania} />
        </>
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
