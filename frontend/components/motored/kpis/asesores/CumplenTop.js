import { Donut, KpiMiniGrid } from '../charts';
import { periodoCorto } from '../periodo';
import { EtiquetaConTip } from '../ventas/CumplimientoTop';
import { COLOR } from '../tokens';
import { ROTULO, TARJETA } from '../ventas/estilos';
import { cumplen, miniKpisAsesores } from './datos';

function TarjetaDonut({ data }) {
  const { segmentos, cumplen: si, evaluados } = cumplen(data);
  return (
    <section aria-label="Asesores que cumplen" style={{ ...TARJETA, flex: '1 1 260px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <h2 style={ROTULO}>Asesores que cumplen · {periodoCorto(data.meses)}</h2>
      <Donut segments={segmentos} centerTitle={`${si} / ${evaluados}`} centerSubtitle="asesores" legend />
    </section>
  );
}

function TarjetaIndicadores({ data }) {
  const items = miniKpisAsesores(data).map((k) => ({ ...k, label: <EtiquetaConTip label={k.label} tip={k.tip} />, key: k.label }));
  return (
    <section aria-label="Indicadores de los asesores" style={{ ...TARJETA, flex: '1.4 1 360px', color: COLOR.ink }}>
      <KpiMiniGrid items={items} />
    </section>
  );
}

/** Top row: asesores that meet the goal (donut) and the six figures. */
export default function CumplenTop({ data }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
      <TarjetaDonut data={data} />
      <TarjetaIndicadores data={data} />
    </div>
  );
}
