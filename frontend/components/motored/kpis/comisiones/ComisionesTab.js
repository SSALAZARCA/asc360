'use client';
/** Comisiones tab, in the design's order: KPI card, strip, ranked list + near tiers, bonuses per line.
 * The step-by-step calculation lives in the asesor detail view. */
import Link from 'next/link';
import { useState } from 'react';
import InfoTooltip from '../../InfoTooltip';
import { CSS_BONOS } from './estilosBonos';
import { KpiMiniGrid, RankBadge, SegmentedToggle, TrafficLightGrid, ZoneStrip } from '../charts';
import { descargarComisionesExcel } from '../../../../lib/motored/kpisApi';
import { enMillones, escalaTramos, filasComision, lineasBono, mosaicoBonos, totalAPagar, COLOR_BONO, numero, leyendaTramos, mesLiquidado, miniKpis, puntosAsesores, celdasCumplimiento, sinPresupuestos, tarjetasCerca } from './datos';
import { COLOR } from '../tokens';
import { CABECERA, LEYENDA, NUM, ROTULO, TARJETA, TITULO } from '../ventas/estilos';

const TIP_MES = 'Las comisiones se calculan sobre el último mes del período elegido.';

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
      <p style={{ margin: 0, fontSize: 12.5, fontWeight: 700, color: COLOR.muted }}>Total a pagar</p>
      <p style={{ margin: '-8px 0 0', fontSize: 34, fontWeight: 700, ...NUM }}>{enMillones(totalAPagar(data), true)}</p>
      <KpiMiniGrid items={items} />
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
  const [abierta, setAbierta] = useState(false);
  const dentro = fila.ancho >= 35;
  const colorTexto = fila.textoSobreBase ? COLOR.ink : '#FFFFFF';
  return (
    <div data-testid="fila-comision" style={{ padding: '2px 0' }}>
      <div className="com-fila">
        <RankBadge rank={rank} />
        <button
          type="button" className="com-nombre" aria-expanded={abierta} onClick={() => setAbierta((v) => !v)}
          style={{ appearance: 'none', border: 0, background: 'transparent', fontFamily: 'inherit', color: 'inherit', textAlign: 'left', padding: 0, minHeight: 44, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
        >
          <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0, flex: 1, gap: 2 }}>
            <span style={{ fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{fila.nombre}</span>
            <span style={{ fontSize: 11.5, color: COLOR.muted, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{fila.sub}</span>
          </span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={COLOR.muted} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ flex: 'none', transform: `rotate(${abierta ? 90 : 0}deg)` }}><path d="M9 6l6 6-6 6" /></svg>
        </button>
        <div className="com-barras" style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <div data-testid="barra-comision" style={{ position: 'relative', height: 22, background: COLOR.wash, borderRadius: 5 }}>
            <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${fila.ancho}%`, background: fila.color, borderRadius: 5, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', paddingRight: 7, boxSizing: 'border-box' }}>
              <span style={{ ...NUM, fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap', ...(dentro ? { color: colorTexto } : { color: COLOR.ink2, position: 'absolute', left: 'calc(100% + 6px)' }) }}>{fila.valor}</span>
            </div>
          </div>
          {fila.bono && (
            <div data-testid="barra-bono" style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
              <span data-testid="barra-bono-relleno" style={{ flex: `0 0 ${fila.bono.ancho}%`, minWidth: 6, maxWidth: '40%', height: 7, borderRadius: 999, background: COLOR_BONO }} />
              <span style={{ fontSize: 11.5, fontWeight: 700, color: COLOR_BONO, minWidth: 0, overflowWrap: 'anywhere' }}>{fila.bono.etiqueta}</span>
            </div>
          )}
          {fila.bajoCompuerta && <span style={{ fontSize: 11, color: COLOR.muted }}>No alcanza el {fila.umbral}% para bonos</span>}
        </div>
        <span data-testid="total-fila" className="com-total" style={{ ...NUM, fontSize: 13.5, fontWeight: 700, whiteSpace: 'nowrap' }}>{fila.total}</span>
        <span className="com-tramo" style={{ fontSize: 11, fontWeight: 700, textAlign: 'center', color: colorTexto, background: fila.color, borderRadius: 999, padding: '3px 0' }}>{fila.tramo}</span>
      </div>
      {abierta && <DetalleBonos fila={fila} />}
    </div>
  );
}

function DetalleBonos({ fila }) {
  return (
    <div data-testid="detalle-bonos" style={{ margin: '6px 0 4px 38px', background: COLOR.wash, border: `1px solid ${COLOR.track}`, borderRadius: 10, padding: '10px 12px' }}>
      <p style={{ margin: '0 0 6px', fontSize: 11.5, fontWeight: 700, color: COLOR.ink2 }}>Bonos por línea</p>
      {fila.detalle.length === 0 && <p style={{ margin: 0, fontSize: 12, color: COLOR.muted }}>Sin líneas de bono configuradas.</p>}
      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexWrap: 'wrap', gap: '6px 20px' }}>
        {fila.detalle.map((d) => (
          <li key={d.linea} data-estado={d.estado} style={{ fontSize: 12, color: d.estado === 'cumple' ? COLOR.ink : COLOR.muted, display: 'inline-flex', alignItems: 'baseline', gap: 6 }}>
            <span aria-hidden="true" style={{ fontWeight: 700, color: d.estado === 'cumple' ? COLOR.good : COLOR.gray500 }}>{d.marca}</span>
            <span>{d.etiqueta}</span>
            <span style={{ ...NUM, fontWeight: 700, color: d.estado === 'cumple' ? COLOR_BONO : COLOR.ink2 }}>{d.texto}</span>
          </li>
        ))}
      </ul>
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

function ChipCabecera({ id, titulo, valor, tinta }) {
  return (
    <span data-testid={id} style={{ display: 'inline-flex', flexDirection: 'column', gap: 2, padding: '8px 14px', borderRadius: 10, background: tinta ? '#FDF3E7' : COLOR.wash, border: `1px solid ${tinta ? '#F3D9B8' : COLOR.track}` }}>
      {titulo && <span style={{ fontSize: 11, fontWeight: 700, color: tinta ? '#7C3A06' : COLOR.muted }}>{titulo}</span>}
      <span style={{ ...NUM, fontSize: 18, fontWeight: 700, color: tinta ? '#7C3A06' : COLOR.ink }}>{valor}</span>
    </span>
  );
}

function TileBono({ t }) {
  return (
    <div data-testid="tile-bono" data-activo={t.activo} style={{ border: `1px solid ${COLOR.track}`, borderRadius: 12, padding: 16, background: t.activo ? COLOR.surface : '#F7F7F5', display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 14, fontWeight: 700, color: t.activo ? COLOR.ink : COLOR.muted }}>{t.etiqueta}</span>
        <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {!t.activo && <span style={{ fontSize: 11, fontWeight: 700, color: COLOR.ink2, background: COLOR.track, borderRadius: 999, padding: '3px 9px' }}>Apagado</span>}
          <span style={{ ...NUM, fontSize: 11, fontWeight: 700, color: t.activo ? '#7C3A06' : COLOR.muted, background: t.activo ? '#FDF3E7' : '#ECECE9', borderRadius: 999, padding: '3px 9px' }}>{t.regla}</span>
        </span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <span style={{ ...NUM, fontSize: 28, fontWeight: 700, letterSpacing: '-.01em', color: t.activo ? COLOR.ink : COLOR.gray500 }}>{t.monto}</span>
        <span style={{ fontSize: 12, color: COLOR.muted }}>{t.quienes}</span>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 5, minHeight: 12 }}>
        {Array.from({ length: t.puntos }, (_, i) => (
          <span key={i} data-testid="punto-ganador" aria-hidden="true" style={{ width: 11, height: 11, borderRadius: 999, boxSizing: 'border-box', background: t.activo ? COLOR_BONO : 'transparent', border: `1.5px solid ${t.activo ? COLOR_BONO : COLOR.gray400}` }} />
        ))}
        {t.mas && <span style={{ ...NUM, fontSize: 11, fontWeight: 700, color: COLOR.muted }}>{t.mas}</span>}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 'auto' }}>
        <div style={{ height: 4, background: '#ECECE9', borderRadius: 999 }}>
          <div data-testid="barra-parte" style={{ width: `${t.ancho}%`, height: 4, background: COLOR_BONO, borderRadius: 999 }} />
        </div>
        <span style={{ ...NUM, fontSize: 11, color: COLOR.muted }}>{t.parteTexto}</span>
      </div>
    </div>
  );
}

function TarjetaBonos({ data }) {
  const m = mosaicoBonos(data);
  return (
    <section aria-label="Bonos por línea" style={{ ...TARJETA, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px 24px', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <h2 style={TITULO}>Bonos por línea · {mesLiquidado(data).largo}</h2>
          <p style={{ margin: '4px 0 0', fontSize: 12.5, color: COLOR.muted }}>Un recuadro por línea. Cada punto es un asesor que ganó el bono.</p>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <ChipCabecera id="chip-pagado" titulo="Pagado en bonos" valor={m.pagado} tinta />
          <ChipCabecera id="chip-ganados" valor={m.ganados} />
        </div>
      </div>
      <div className="bon-mosaico">{m.tiles.map((t) => <TileBono key={t.id} t={t} />)}</div>
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
      <style>{CSS_BONOS}</style>
      <ChipMes data={data} />
      {sinPresupuestos(data) ? <SinPresupuestoMes data={data} /> : (
        <>
          <TarjetaKpi data={data} />
          <TarjetaFranja data={data} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
            <TarjetaComision data={data} filtros={filtros} />
            <TarjetaCerca data={data} />
          </div>
          {lineasBono(data).length > 0 && <TarjetaBonos data={data} />}
        </>
      )}
    </section>
  );
}
