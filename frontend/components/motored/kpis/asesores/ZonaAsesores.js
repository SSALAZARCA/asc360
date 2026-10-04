import { ZoneStrip } from '../charts';
import { periodoCorto } from '../periodo';
import { COLOR } from '../tokens';
import { zonasSemaforo } from '../ventas/datos';
import { CABECERA, TARJETA, TITULO } from '../ventas/estilos';
import LeyendaZonas from '../ventas/LeyendaZonas';
import SinPresupuesto from '../ventas/SinPresupuesto';
import { puntosAsesores } from './datos';

function Franja({ puntos, zonas }) {
  return (
    <ZoneStrip
      dots={puntos} min={0} max={150} lines={[zonas.ambar, zonas.verde, 100]} ariaLabel="Cumplimiento de cada asesor"
      zones={[{ hasta: zonas.ambar, bg: COLOR.badSoft }, { hasta: zonas.verde, bg: COLOR.midSoft }, { hasta: 150, bg: COLOR.goodSoft }]}
      ticks={[
        { value: 0, label: '0%' }, { value: zonas.ambar, label: `${zonas.ambar}%`, strong: true },
        { value: zonas.verde, label: `${zonas.verde}%`, strong: true }, { value: 100, label: 'Meta', strong: true }, { value: 150, label: '150%+' },
      ]}
    />
  );
}

/** "Dónde cae cada asesor": every asesor with budget as a dot over the compliance zones. */
export default function ZonaAsesores({ data }) {
  const zonas = zonasSemaforo(data, 'asesores');
  const puntos = puntosAsesores(data);
  const sinCedula = data.cumplimiento.advertencias?.personas_sin_cedula ?? 0;
  return (
    <section aria-label="Dónde cae cada asesor" style={TARJETA}>
      <div style={CABECERA}>
        <h2 style={TITULO}>Dónde cae cada asesor · cumplimiento {periodoCorto(data.meses)}</h2>
        {puntos.length > 0 && <LeyendaZonas zonas={zonas} />}
      </div>
      {puntos.length > 0 ? <Franja puntos={puntos} zonas={zonas} /> : <SinPresupuesto />}
      {sinCedula > 0 && (
        <p style={{ margin: '8px 0 0', fontSize: 11.5, color: COLOR.muted }}>
          {sinCedula} {sinCedula === 1 ? 'asesor sin cédula en el maestro no se puede cruzar' : 'asesores sin cédula en el maestro no se pueden cruzar'} con el presupuesto.
        </p>
      )}
    </section>
  );
}
