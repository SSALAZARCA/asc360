'use client';
import { useState } from 'react';
import { SegmentedToggle, TrafficLightGrid } from '../charts';
import { periodoCorto } from '../periodo';
import CumplimientoBarras from './CumplimientoBarras';
import { filasCumplimiento, hayPresupuesto, zonasSemaforo } from './datos';
import LeyendaZonas from './LeyendaZonas';
import SinPresupuesto from './SinPresupuesto';
import { CABECERA, TARJETA, TITULO } from './estilos';

const VISTAS = [{ id: 'semaforo', label: 'Semáforo' }, { id: 'barras', label: 'Barras' }];

function Semaforo({ filas, zonas }) {
  const items = filas.map((f) => ({ id: f.id, name: f.nombre, pct: f.fraccion, detail: f.fraccion === null ? 'Sin presupuesto' : undefined }));
  return <div style={{ marginTop: 14 }}><TrafficLightGrid items={items} cortes={{ verde_desde: zonas.verde, ambar_desde: zonas.ambar }} /></div>;
}

/** "Cumplimiento por tienda": traffic lights or bars, with the toggle next to the title. */
export default function CumplimientoPorTienda({ data }) {
  const [vista, setVista] = useState('semaforo');
  const zonas = zonasSemaforo(data);
  const filas = filasCumplimiento(data);
  const conPresupuesto = hayPresupuesto(data);
  return (
    <section aria-label="Cumplimiento por tienda" style={TARJETA}>
      <div style={CABECERA}>
        <h2 style={TITULO}>Cumplimiento por tienda · {periodoCorto(data.meses)}</h2>
        {conPresupuesto && <SegmentedToggle options={VISTAS} value={vista} onChange={setVista} />}
        {conPresupuesto && <LeyendaZonas zonas={zonas} />}
      </div>
      {!conPresupuesto && <SinPresupuesto />}
      {conPresupuesto && vista === 'semaforo' && <Semaforo filas={filas} zonas={zonas} />}
      {conPresupuesto && vista === 'barras' && <CumplimientoBarras filas={filas} zonas={zonas} />}
    </section>
  );
}
