'use client';
/** Comisiones tab, in the design's order: KPI card + how it is calculated, strip, ranked list + near tiers. */
import Link from 'next/link';
import { useState } from 'react';
import InfoTooltip from '../../InfoTooltip';
import { KpiMiniGrid, RankBadge, SegmentedToggle, TrafficLightGrid, ZoneStrip } from '../charts';
import { descargarComisionesExcel } from '../../../../lib/motored/kpisApi';
import { enMillones, ejemploDe, escalaTramos, filasComision, leyendaTramos, mesLiquidado, miniKpis, pasosDeCalculo, puntosAsesores, celdasCumplimiento, sinPresupuestos, tarjetasCerca } from './datos';
import { COLOR } from '../tokens';
import { CABECERA, LEYENDA, NUM, ROTULO, TARJETA, TITULO } from '../ventas/estilos';

const TIP_MES = 'Las comisiones se calculan sobre el último mes del período elegido.';
const TIP_META = 'La meta de cada asesor es el presupuesto que se le cargó en Maestros → Presupuestos para el mes.';

function ChipMes({ data }) {
  return (
    <div data-testid="chip-mes" style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 6, background: COLOR.infoSoft, color: COLOR.info, borderRadius: 999, padding: '4px 12px', fontSize: 12.5, fontWeight: 700 }}>
      <span>Mes liquidado: {mesLiquidado(data).completo}</span>
      <InfoTooltip text={TIP_MES} />
    </div>
  );
}

function TarjetaKpi({ data }) {
  const items = miniKpis(data).map((k) => ({ ...k, key: k.label, label: <>{k.label} <InfoTooltip text={k.tip} /></> }));
  return (
    <section aria-label="Comisiones del mes" style={{ ...TARJETA, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <h2 style={ROTULO}>Comisiones · {mesLiquidado(data).largo}</h2>
      <p style={{ margin: 0, fontSize: 34, fontWeight: 700, ...NUM }}>{enMillones(data.resumen.comision_total, true)}</p>
      <KpiMiniGrid items={items} />
    </section>
  );
}

function Paso({ paso }) {
  return (
    <div style={{ padding: 12, borderRadius: 12, background: COLOR.infoSoft, display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
      <span style={{ width: 24, height: 24, borderRadius: 999, background: COLOR.info, color: '#FFFFFF', fontSize: 12, fontWeight: 700, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>{paso.n}</span>
      <span style={{ fontSize: 13, fontWeight: 700 }}>{paso.titulo}{paso.n === '1' && <> <InfoTooltip text={TIP_META} /></>}</span>
      <span style={{ fontSize: 12, color: COLOR.ink2 }}>{paso.regla}</span>
      <span style={{ ...NUM, marginTop: 'auto', fontSize: 12, fontWeight: 700, color: COLOR.info, background: COLOR.surface, borderRadius: 8, padding: '5px 8px' }}>{paso.ejemplo}</span>
    </div>
  );
}

function TarjetaPasos({ data }) {
  return (
    <section aria-label="Cómo se calcula la comisión" style={TARJETA}>
      <h2 style={TITULO}>Cómo se calcula la comisión</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10, marginTop: 14 }}>
        {pasosDeCalculo(data).map((p) => <Paso key={p.n} paso={p} />)}
      </div>
      <p style={{ margin: '10px 0 0', fontSize: 12, color: COLOR.muted }}>{ejemploDe(data)}</p>
    </section>
  );
}

function Franja({ data }) {
  const escala = escalaTramos(data.tramos);
  return (
    <ZoneStrip
      dots={puntosAsesores(data, escala)} min={0} max={100} lines={escala.lineas} zones={escala.zonas} ticks={escala.ticks}
      ariaLabel="Cumplimiento de cada asesor y su tramo"
    />
  );
}

function TarjetaFranja({ data }) {
  return (
    <section aria-label="Dónde cae cada asesor" style={TARJETA}>
      <div style={CABECERA}>
        <h2 style={TITULO}>Dónde cae cada asesor · {mesLiquidado(data).largo}</h2>
        <div style={LEYENDA}>
          {leyendaTramos(data).map((t) => (
            <span key={t.nombre} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 10, height: 10, borderRadius: 3, background: t.color }} />
              <span>{t.texto}<strong style={{ ...NUM, color: COLOR.ink }}>{t.n}</strong></span>
            </span>
          ))}
        </div>
      </div>
      <Franja data={data} />
    </section>
  );
}

function FilaComision({ fila, rank }) {
  const dentro = fila.ancho >= 35;
  return (
    <div data-testid="fila-comision" style={{ display: 'grid', gridTemplateColumns: '28px minmax(120px, 200px) minmax(0, 1fr) 64px', gap: 10, alignItems: 'center' }}>
      <RankBadge rank={rank} />
      <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <span style={{ fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{fila.nombre}</span>
        <span style={{ fontSize: 11.5, color: COLOR.muted, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{fila.sub}</span>
      </span>
      <div style={{ position: 'relative', height: 22, background: COLOR.wash, borderRadius: 5 }}>
        <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${fila.ancho}%`, background: fila.color, borderRadius: 5, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', paddingRight: 7, boxSizing: 'border-box' }}>
          <span style={{ ...NUM, fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap', ...(dentro ? { color: '#FFFFFF' } : { color: COLOR.ink2, position: 'absolute', left: 'calc(100% + 6px)' }) }}>{fila.valor}</span>
        </div>
      </div>
      <span style={{ fontSize: 11, fontWeight: 700, textAlign: 'center', color: '#FFFFFF', background: fila.color, borderRadius: 999, padding: '3px 0' }}>{fila.tramo}</span>
    </div>
  );
}

function BotonExcel({ data, filtros }) {
  const [estado, setEstado] = useState({ ocupado: false, error: null });
  const descargar = async () => {
    setEstado({ ocupado: true, error: null });
    try {
      await descargarComisionesExcel(filtros, data.mes_liquidado);
      setEstado({ ocupado: false, error: null });
    } catch {
      setEstado({ ocupado: false, error: 'No pudimos descargar el Excel. Intentá de nuevo.' });
    }
  };
  return (
    <>
      <button
        type="button" onClick={descargar} disabled={estado.ocupado}
        title="Descarga las comisiones del mes liquidado, con la cédula de cada asesor."
        style={{ appearance: 'none', border: `1px solid ${COLOR.line}`, background: COLOR.surface, color: COLOR.ink, fontFamily: 'inherit', fontSize: 12.5, fontWeight: 700, minHeight: 36, padding: '8px 14px', borderRadius: 10, cursor: estado.ocupado ? 'default' : 'pointer', opacity: estado.ocupado ? 0.6 : 1 }}
      >
        {estado.ocupado ? 'Descargando…' : 'Descargar Excel'}
      </button>
      {estado.error && <p role="alert" style={{ flexBasis: '100%', margin: 0, fontSize: 12.5, color: 'var(--motored-danger, #C0392B)' }}>{estado.error}</p>}
    </>
  );
}

function TarjetaComision({ data, filtros }) {
  const [vista, setVista] = useState('pago');
  return (
    <section aria-label="Comisión por asesor" style={TARJETA}>
      <div style={CABECERA}>
        <h2 style={TITULO}>Comisión por asesor · {mesLiquidado(data).largo}</h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <SegmentedToggle options={[{ id: 'pago', label: 'Comisión' }, { id: 'cumpl', label: 'Cumplimiento' }]} value={vista} onChange={setVista} />
          <BotonExcel data={data} filtros={filtros} />
        </div>
      </div>
      <div style={{ marginTop: 14, maxHeight: 420, overflowY: 'auto', paddingRight: 8 }}>
        {vista === 'pago' ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {filasComision(data).map((f, i) => <FilaComision key={f.id} fila={f} rank={i + 1} />)}
          </div>
        ) : <TrafficLightGrid items={celdasCumplimiento(data)} cortes={data.reglas.semaforo} />}
      </div>
    </section>
  );
}

function TarjetaCerca({ data }) {
  const tarjetas = tarjetasCerca(data);
  return (
    <section aria-label="Cerca de subir de tramo" style={TARJETA}>
      <h2 style={TITULO}>Cerca de subir de tramo</h2>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 14, maxHeight: 420, overflowY: 'auto', paddingRight: 6 }}>
        {tarjetas.length === 0 && <p style={{ margin: 0, fontSize: 13, color: COLOR.muted }}>Nadie está cerca de subir de tramo este mes.</p>}
        {tarjetas.map((c) => (
          <div key={c.id} data-testid="fila-cerca" style={{ padding: 12, borderRadius: 12, border: `1px solid ${COLOR.track}`, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'baseline' }}>
              <span style={{ fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.nombre}</span>
              <span style={{ ...NUM, flex: 'none', fontSize: 12, fontWeight: 700, borderRadius: 999, padding: '2px 8px', background: COLOR.goodSoft, color: COLOR.goodInk }}>{c.gana}</span>
            </div>
            <div style={{ position: 'relative', height: 10, background: COLOR.wash, borderRadius: 999 }}>
              <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${c.ancho}%`, background: c.color, borderRadius: 999 }} />
            </div>
            <span style={{ fontSize: 12, color: COLOR.ink2 }}>{c.actual} → {c.meta} · le faltan <strong style={NUM}>{c.falta}</strong> para {c.siguiente}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function SinPresupuestoMes({ data }) {
  return (
    <p style={{ margin: 0, fontSize: 14 }}>
      Cargá los presupuestos de {mesLiquidado(data).largo} de {mesLiquidado(data).anio} para calcular comisiones.{' '}
      <Link href="/motored/maestros" style={{ color: COLOR.info }}>Ir a Maestros → Presupuestos</Link>
    </p>
  );
}

export default function ComisionesTab({ data, filtros }) {
  return (
    <section aria-label="Comisiones" style={{ display: 'flex', flexDirection: 'column', gap: 18, minWidth: 0 }}>
      <ChipMes data={data} />
      {sinPresupuestos(data) ? <SinPresupuestoMes data={data} /> : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 16 }}>
            <TarjetaKpi data={data} />
            <TarjetaPasos data={data} />
          </div>
          <TarjetaFranja data={data} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
            <TarjetaComision data={data} filtros={filtros} />
            <TarjetaCerca data={data} />
          </div>
        </>
      )}
    </section>
  );
}
