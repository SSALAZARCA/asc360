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
 */
import { useState } from 'react';

export default function MaestrosTabs({ tabs }) {
  const [activeId, setActiveId] = useState(tabs[0].id);
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
          </button>
        ))}
      </div>
      {active.render()}
    </div>
  );
}
