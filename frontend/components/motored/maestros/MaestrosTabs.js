'use client';
/**
 * frontend/components/motored/maestros/MaestrosTabs.js
 *
 * Tab switcher for the 4 masters (sdd/motored-pedidos-cimientos, proposal
 * §7.12: "Maestros screen, 4 tabs: Sucursales · Bodegas · Referencias ·
 * Proveedores"). ONE page, one route (`/motored/maestros`) -- not 4
 * separate sidebar entries. Visual pattern matches the real design
 * system's underline tabs (`.motored-tab-bar`/`.motored-tab`, see
 * `app/motored/layout.js`), not an invented one.
 *
 * Only the ACTIVE tab's component is mounted -- switching tabs doesn't
 * carry the other three's API calls/state along for no reason.
 *
 * Per direct user feedback, there is no separate "Salud de maestros" tab
 * anymore -- instead, each tab that has an `entidadSalud` gets a small
 * traffic-light dot next to its label, sourced from the SAME `GET
 * /maestros/salud` response (`backend/app/motored/services/salud.py`),
 * fetched ONCE here and derived per-entidad from each hallazgo's own
 * `entidad`/`bloqueante` fields -- no new backend endpoint needed, since
 * the health checks were already tagged by entity.
 */
import { useEffect, useState } from 'react';
import { getSalud } from '../../../lib/motored/api';

const ESTADO_COLOR = {
  verde: 'var(--motored-success, #15803d)',
  advertencia: 'var(--motored-warning, #d97706)',
  bloqueado: 'var(--motored-danger, #c0392b)',
};

function estadoPorEntidad(hallazgos) {
  const porEntidad = {};
  for (const h of hallazgos) {
    if (h.bloqueante) {
      porEntidad[h.entidad] = 'bloqueado';
    } else if (porEntidad[h.entidad] !== 'bloqueado') {
      porEntidad[h.entidad] = 'advertencia';
    }
  }
  return porEntidad;
}

function useSaludPorEntidad() {
  const [porEntidad, setPorEntidad] = useState({});
  useEffect(() => {
    getSalud()
      .then((salud) => setPorEntidad(estadoPorEntidad(salud.hallazgos)))
      .catch((err) => {
        // No bloquea la pantalla por esto -- los dots son un indicador
        // secundario, no la función principal de la pestaña -- pero el
        // fallo no debe desaparecer sin dejar rastro.
        console.error('No se pudo cargar la salud de maestros para los indicadores de pestaña:', err);
      });
  }, []);
  return porEntidad;
}

function EstadoDot({ estado }) {
  return (
    <span
      title={estado === 'bloqueado' ? 'Hay un problema bloqueante' : estado === 'advertencia' ? 'Hay advertencias' : 'Todo en orden'}
      style={{
        display: 'inline-block', width: '8px', height: '8px', borderRadius: '999px',
        marginLeft: '6px', background: ESTADO_COLOR[estado] || ESTADO_COLOR.verde,
      }}
    />
  );
}

export default function MaestrosTabs({ tabs }) {
  const [activeId, setActiveId] = useState(tabs[0].id);
  const saludPorEntidad = useSaludPorEntidad();
  const active = tabs.find((t) => t.id === activeId);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div className="motored-tab-bar">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`motored-tab${tab.id === activeId ? ' is-active' : ''}`}
            onClick={() => setActiveId(tab.id)}
          >
            {tab.label}
            {tab.entidadSalud && <EstadoDot estado={saludPorEntidad[tab.entidadSalud] || 'verde'} />}
          </button>
        ))}
      </div>
      {active.render()}
    </div>
  );
}
