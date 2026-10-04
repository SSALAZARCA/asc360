import { Donut, KpiMiniGrid } from '../charts';
import { EtiquetaConTip } from '../ventas/CumplimientoTop';
import { COLOR } from '../tokens';
import { NUM, ROTULO, TARJETA } from '../ventas/estilos';
import { miniKpisTiendas, tendencia } from './datos';

function Leyenda({ segmentos }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: '1 1 140px' }}>
      {segmentos.map((s) => (
        <div key={s.label} data-testid="tendencia-leyenda" style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13 }}>
          <span style={{ width: 12, height: 12, borderRadius: 999, background: s.color, flex: 'none' }} />
          <span style={{ flex: 1 }}>{s.label}</span>
          <strong style={NUM}>{s.value}</strong>
        </div>
      ))}
    </div>
  );
}

function TarjetaTendencia({ data }) {
  const { segmentos, total } = tendencia(data);
  return (
    <section aria-label="Tendencia de las tiendas" style={{ ...TARJETA, flex: '1 1 260px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <h2 style={ROTULO}>Tendencia · últimos 3 meses vs 3 anteriores</h2>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <Donut segments={segmentos} centerTitle={String(total)} centerSubtitle="tiendas" />
        <Leyenda segmentos={segmentos} />
      </div>
    </section>
  );
}

function TarjetaIndicadores({ data }) {
  const items = miniKpisTiendas(data).map((k) => ({ ...k, label: <EtiquetaConTip label={k.label} tip={k.tip} />, key: k.label }));
  return (
    <section aria-label="Indicadores de las tiendas" style={{ ...TARJETA, flex: '2 1 420px', color: COLOR.ink }}>
      <KpiMiniGrid items={items} />
    </section>
  );
}

/** Top row: stores by trend (donut) and the six figures that name a store. */
export default function TendenciaTop({ data }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
      <TarjetaTendencia data={data} />
      <TarjetaIndicadores data={data} />
    </div>
  );
}
