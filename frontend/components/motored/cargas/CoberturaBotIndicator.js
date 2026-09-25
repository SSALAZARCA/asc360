'use client';
/**
 * frontend/components/motored/cargas/CoberturaBotIndicator.js
 *
 * "Última carga por bot" indicator (sdd/motored-ventas-perdidas-bot, Phase
 * 7, tasks 7.1/7.2; design D8 slice S5, `demanda_perdida` spec requirement
 * "Most-recent BOT-origin date is a non-blocking visibility aid"). Excel
 * stays the contingency path for DEMANDA_PERDIDA -- this only tells an
 * advisor/admin whether bot Lore already covered a sucursal's recent days,
 * so they know if the Excel upload is actually needed today.
 *
 * Sourced from `GET /demanda-perdida/cobertura-bot`
 * (`backend/app/motored/api/demanda_perdida.py`, shipped in Phase 6):
 * `[{ sucursal_id, ultima_fecha_bot }]`, ONE row per sucursal that has at
 * least one ACTIVA bot registration -- never a single global date, per the
 * spec's own "per sucursal" wording.
 *
 * Non-blocking by construction (spec: "An overlapping Excel upload is
 * accepted, not blocked"): this component owns no upload/validation logic
 * at all, renders nothing while loading, and renders nothing -- silently,
 * no error banner -- on an empty result or a failed fetch. It is placed
 * next to the Excel "Subir archivo" control (`MovimientoTab`) but never
 * gates it.
 */
import { useEffect, useState } from 'react';
import { getCoberturaBot, listMaestros } from '../../../lib/motored/api';

export default function CoberturaBotIndicator() {
  const [cobertura, setCobertura] = useState([]);
  const [nombrePorSucursal, setNombrePorSucursal] = useState({});
  const [mostrarDetalle, setMostrarDetalle] = useState(false);

  useEffect(() => {
    let cancelado = false;
    Promise.all([getCoberturaBot(), listMaestros('sucursales')])
      .then(([coberturaData, sucursales]) => {
        if (cancelado) return;
        setCobertura(Array.isArray(coberturaData) ? coberturaData : []);
        setNombrePorSucursal(
          Object.fromEntries((sucursales || []).map((s) => [s.id, s.nombre]))
        );
      })
      .catch(() => {
        // Advisory-only (spec): a failed fetch must never surface an error
        // and must never affect the Excel upload flow this sits next to.
        if (!cancelado) setCobertura([]);
      });
    return () => {
      cancelado = true;
    };
  }, []);

  if (cobertura.length === 0) return null;

  const filas = [...cobertura].sort((a, b) =>
    a.ultima_fecha_bot < b.ultima_fecha_bot ? 1 : -1
  );
  const masReciente = filas[0];
  const nombreMasReciente = nombrePorSucursal[masReciente.sucursal_id] || masReciente.sucursal_id;

  return (
    <div style={{ fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
      <button
        type="button"
        onClick={() => setMostrarDetalle((v) => !v)}
        style={{
          background: 'none',
          border: 'none',
          padding: 0,
          color: 'inherit',
          cursor: 'pointer',
          textDecoration: 'underline',
        }}
      >
        Última carga por bot: {nombreMasReciente} — {masReciente.ultima_fecha_bot} ({filas.length} sucursal{filas.length === 1 ? '' : 'es'})
      </button>

      {mostrarDetalle && (
        <ul style={{ margin: '0.5rem 0 0', padding: 0, listStyle: 'none', maxHeight: '160px', overflowY: 'auto' }}>
          {filas.map((f) => (
            <li key={f.sucursal_id}>
              {nombrePorSucursal[f.sucursal_id] || f.sucursal_id}: {f.ultima_fecha_bot}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
