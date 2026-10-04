'use client';
import { COLOR } from '../tokens';
import {
  PRESETS, alternarMes, etiquetaPeriodo, mesesDelAnio, MESES_CORTOS, presetMeses, resumenPeriodo,
} from '../periodo';
import FilterPopover from './FilterPopover';
import { TITULO_POPOVER, chip } from './estilos';

const sonIguales = (a, b) => a.length === b.length && a.every((m, i) => m === b[i]);

function Presets({ meses, disponibles, ultimoMes, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
      {PRESETS.map((p) => {
        const destino = presetMeses(p.id, ultimoMes).filter((m) => disponibles.includes(m));
        const activo = sonIguales([...meses].sort(), destino);
        const aplicar = () => destino.length && onChange({ meses: destino });
        return (
          <button key={p.id} type="button" aria-pressed={activo} onClick={aplicar} style={chip(activo)}>
            {p.label}
          </button>
        );
      })}
    </div>
  );
}

function Chips({ meses, disponibles, ultimoMes, onChange }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
      {mesesDelAnio(ultimoMes).map((mes, i) => {
        const activo = meses.includes(mes);
        // An unavailable month can never be added, but a selected one can always be removed.
        const sinDatos = !disponibles.includes(mes) && !activo;
        const pulsar = () => {
          if (sinDatos) return;
          const siguiente = alternarMes(meses, mes);
          if (siguiente.length) onChange({ meses: siguiente });
        };
        return (
          <button key={mes} type="button" aria-pressed={activo} aria-disabled={sinDatos} onClick={pulsar} style={chip(activo, sinDatos)}>
            {MESES_CORTOS[i]}
          </button>
        );
      })}
    </div>
  );
}

export default function PeriodoFilter({ opciones, filtros, onChange, abierto, onToggle, onClose }) {
  const { ultimo_mes: ultimoMes, meses_disponibles: disponibles } = opciones;
  return (
    <FilterPopover
      rotulo="Período" valor={etiquetaPeriodo(filtros.meses, ultimoMes)} dialogo="Elegir período" lado="left"
      abierto={abierto} onToggle={onToggle} onClose={onClose} resumen={resumenPeriodo(filtros.meses.length)}
    >
      <Presets meses={filtros.meses} disponibles={disponibles} ultimoMes={ultimoMes} onChange={onChange} />
      <div style={{ ...TITULO_POPOVER, color: COLOR.soft }}>{ultimoMes.slice(0, 4)} · elegí uno o varios meses</div>
      <Chips meses={filtros.meses} disponibles={disponibles} ultimoMes={ultimoMes} onChange={onChange} />
    </FilterPopover>
  );
}
