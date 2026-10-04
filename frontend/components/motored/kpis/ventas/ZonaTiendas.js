import { ZoneStrip } from '../charts';
import { periodoCorto } from '../periodo';
import { COLOR, TONO } from '../tokens';
import { filasCumplimiento, hayPresupuesto, zonasSemaforo } from './datos';
import LeyendaZonas from './LeyendaZonas';
import SinPresupuesto from './SinPresupuesto';
import { CABECERA, TARJETA, TITULO } from './estilos';

const tono = (puntos, zonas) => (puntos >= zonas.verde ? 'good' : puntos >= zonas.ambar ? 'mid' : 'bad');

function Franja({ data, zonas }) {
  const puntos = filasCumplimiento(data).filter((f) => f.fraccion !== null).map((f) => ({
    value: f.fraccion * 100, color: TONO[tono(f.fraccion * 100, zonas)].color, tip: `${f.nombre} · ${(f.fraccion * 100).toFixed(1).replace('.', ',')}%`,
  }));
  return (
    <ZoneStrip
      dots={puntos} min={0} max={150} lines={[zonas.ambar, zonas.verde, 100]} ariaLabel="Cumplimiento de cada tienda"
      zones={[{ hasta: zonas.ambar, bg: COLOR.badSoft }, { hasta: zonas.verde, bg: COLOR.midSoft }, { hasta: 150, bg: COLOR.goodSoft }]}
      ticks={[
        { value: 0, label: '0%' }, { value: zonas.ambar, label: `${zonas.ambar}%`, strong: true },
        { value: zonas.verde, label: `${zonas.verde}%`, strong: true }, { value: 100, label: 'Meta', strong: true },
        { value: 150, label: '150%+' },
      ]}
    />
  );
}

/** "Dónde cae cada tienda": every store with budget as a dot over the compliance zones. */
export default function ZonaTiendas({ data }) {
  const zonas = zonasSemaforo(data);
  const periodo = periodoCorto(data.meses);
  return (
    <section aria-label="Dónde cae cada tienda" style={TARJETA}>
      <div style={CABECERA}>
        <h2 style={TITULO}>Dónde cae cada tienda · cumplimiento {periodo}</h2>
        {hayPresupuesto(data) && <LeyendaZonas zonas={zonas} />}
      </div>
      {hayPresupuesto(data) ? <Franja data={data} zonas={zonas} /> : <SinPresupuesto />}
    </section>
  );
}
