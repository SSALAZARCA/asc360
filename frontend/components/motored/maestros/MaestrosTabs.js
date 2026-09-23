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
 *
 * `group` (sdd/motored-cargas-tipo-declarado; design D4): the tab bar grew
 * from 4 to 10 tabs when the 6 movement types were consolidated in here
 * (proposal decision #2, "ONE screen"). Rather than a second route or a
 * second `.motored-tab-bar`, each `TABS` entry now carries an optional
 * `group` ('Maestros' | 'Movimientos') and this component renders a small
 * uppercase label right before the FIRST tab of each new group -- a label
 * change inside the same bar, not a new screen, per the owner's "keep
 * Maestros / single route" ruling. `.motored-tab-bar`'s existing CSS uses
 * `flex-wrap`, which SHOULD handle 10 tabs on a narrow viewport, but this
 * has NOT been confirmed in a real browser in this batch (no live backend
 * was reachable in this environment to authenticate into `/motored/
 * maestros`) -- jsdom cannot catch layout/overflow at all, so this remains
 * an open live-verification item per the standing project rule, not a
 * closed one.
 */
import { Fragment, useEffect, useState } from 'react';
import { getSalud } from '../../../lib/motored/api';

const groupLabelStyle = {
  display: 'flex', alignItems: 'center', padding: '0 0.35rem',
  color: 'var(--motored-text-soft, #8a8a8a)', textTransform: 'uppercase',
  fontSize: '0.65rem', fontWeight: 700, letterSpacing: '0.04em',
};

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

  let grupoAnterior = null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div className="motored-tab-bar">
        {tabs.map((tab) => {
          const mostrarRotuloGrupo = Boolean(tab.group) && tab.group !== grupoAnterior;
          if (tab.group) grupoAnterior = tab.group;
          return (
            <Fragment key={tab.id}>
              {mostrarRotuloGrupo && <span style={groupLabelStyle}>{tab.group}</span>}
              <button
                type="button"
                className={`motored-tab${tab.id === activeId ? ' is-active' : ''}`}
                onClick={() => setActiveId(tab.id)}
              >
                {tab.label}
                {tab.entidadSalud && <EstadoDot estado={saludPorEntidad[tab.entidadSalud] || 'verde'} />}
              </button>
            </Fragment>
          );
        })}
      </div>
      {active.render()}
    </div>
  );
}
