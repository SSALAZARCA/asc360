import { Chip, Donut, RankBadge, StackedBar100 } from '../charts';
import { millones, pct } from '../format';
import { periodoCorto } from '../periodo';
import { COLOR } from '../tokens';
import { bloquesVentana, mesCorto } from './datos';
import { CABECERA, NUM, TARJETA, TITULO } from './estilos';
import NotaVentana from './NotaVentana';
import { barrasMensuales, chipParticipacion, mezclaLineas } from './tecniredDatos';

const FICHA = { textAlign: 'center', padding: 8, borderRadius: 10, background: COLOR.infoSoft };

function Fichas({ tecnired }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, width: '100%' }}>
      <div style={FICHA}><div style={{ ...NUM, fontSize: 18, fontWeight: 700 }}>{Math.round(tecnired.clientes).toLocaleString('es-CO')}</div><div style={{ fontSize: 11, color: COLOR.muted }}>clientes</div></div>
      <div style={FICHA}><div style={{ ...NUM, fontSize: 18, fontWeight: 700 }}>{millones(tecnired.venta_por_cliente, 1)}</div><div style={{ fontSize: 11, color: COLOR.muted }}>por cliente</div></div>
    </div>
  );
}

function Dona({ data }) {
  const { tecnired, total } = bloquesVentana(data);
  const resto = Math.max(total.venta.total - tecnired.venta, 0);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, flex: '0 0 170px' }}>
      <Donut
        size={160} formatValue={millones} centerTitle={millones(tecnired.venta)} centerSubtitle={`${pct(tecnired.pct)} del total`}
        segments={[{ label: 'Tecnired', value: tecnired.venta, color: COLOR.info }, { label: 'Resto de la venta', value: resto, color: COLOR.infoSoft }]}
      />
      <Fichas tecnired={tecnired} />
    </div>
  );
}

function BarrasMes({ barras }) {
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, height: 170, borderBottom: `1px solid ${COLOR.track}` }}>
        {barras.map((b) => (
          <div key={b.mes} style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', gap: 4, height: '100%' }}>
            <span style={{ ...NUM, fontSize: 10.5, fontWeight: 700, whiteSpace: 'nowrap' }}>{b.texto}</span>
            <div style={{ width: '100%', maxWidth: 38, height: `${b.alto * 0.8}%`, background: COLOR.info, borderRadius: '6px 6px 0 0' }} />
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
        {barras.map((b) => (
          <div key={b.mes} style={{ flex: 1, minWidth: 0, textAlign: 'center' }}>
            <div style={{ fontSize: 11.5, color: COLOR.muted }}>{mesCorto(b.mes)}</div>
            <div style={{ ...NUM, fontSize: 10.5, fontWeight: 700, color: COLOR.info }}>{pct(b.fraccion)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function MezclaLineas({ data }) {
  const segmentos = mezclaLineas(data);
  const total = segmentos.reduce((t, s) => t + s.value, 0);
  return (
    <>
      <div style={{ marginTop: 16 }}><StackedBar100 segments={segmentos} height={14} /></div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginTop: 8 }}>
        {segmentos.map((s) => (
          <span key={s.label} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: COLOR.ink2 }}>
            <span style={{ width: 10, height: 10, borderRadius: 3, background: s.color }} />{s.label} <strong style={NUM}>{pct(total > 0 ? s.value / total : null)}</strong>
          </span>
        ))}
      </div>
    </>
  );
}

function TarjetaTecnired({ data }) {
  const barras = barrasMensuales(data);
  const chip = chipParticipacion(barras);
  return (
    <section aria-label="Clientes Tecnired" style={{ ...TARJETA, flex: '1.7 1 420px' }}>
      <div style={CABECERA}>
        <h2 style={TITULO}>Clientes Tecnired · {periodoCorto(bloquesVentana(data).meses)}</h2>
        {chip && <Chip text={chip.texto} variant={chip.variante} />}
      </div>
      <NotaVentana />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 22, alignItems: 'center', marginTop: 14 }}>
        <Dona data={data} />
        <div style={{ flex: '1 1 260px', minWidth: 0 }}>
          <BarrasMes barras={barras} />
          <MezclaLineas data={data} />
        </div>
      </div>
    </section>
  );
}

function Top5({ data }) {
  const top = data.tecnired.top5;
  const maximo = Math.max(1, ...top.map((c) => c.venta));
  return (
    <section aria-label="Top 5 clientes Tecnired" style={{ ...TARJETA, flex: '1 1 300px' }}>
      <h2 style={TITULO}>Top 5 clientes Tecnired · {periodoCorto(data.meses)}</h2>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 16 }}>
        {top.map((c, i) => (
          <div key={c.nit} data-testid="top-cliente" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <RankBadge rank={i + 1} size={30} />
            <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 5 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 13 }}>
                <span style={{ fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.razon_social}</span>
                <span style={{ ...NUM, fontWeight: 700 }}>{millones(c.venta)}</span>
              </div>
              <div style={{ height: 10, background: COLOR.track, borderRadius: 999, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${(c.venta / maximo) * 100}%`, background: COLOR.info, borderRadius: 999 }} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

/** Tecnired block: donut + monthly bars + line mix on the left, top 5 clients beside it (wraps on tablet). */
export default function TecniredSection({ data }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
      <TarjetaTecnired data={data} />
      <Top5 data={data} />
    </div>
  );
}
