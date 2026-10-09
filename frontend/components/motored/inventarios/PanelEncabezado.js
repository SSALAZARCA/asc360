'use client';
/**
 * Header of the live panel (WU12): title, start and snapshot times, the
 * refresh cadence with "Actualizar ahora", and a tab per open conteo the
 * user can see (the prototype's per-store chips; the API gives no
 * per-store progress, so the chips carry the store name only).
 */
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { listarConteos } from '../../../lib/motored/conteosApi';
import { fechaHoraBogota, horaBogota } from '../../../lib/motored/fechas';
import { CONTEOS_PATH } from '../../../lib/motored/session';
import { ESTADOS_ABIERTOS, labelEstado } from './conteosFormato';
import { INTERVALO_VISIBLE_MS } from './usePollingConteo';
import { mutedStyle, rotuloStyle, tituloStyle } from './estilos';

const chip = (activo) => ({
  minHeight: '44px', padding: '0 16px', borderRadius: 'var(--motored-radius-pill, 999px)', fontWeight: activo ? 700 : 600,
  border: activo ? '2px solid var(--motored-brand, #e20714)' : '1px solid var(--motored-border, #e4e4e7)',
  background: activo ? 'var(--motored-brand-soft, #fde8ea)' : 'var(--motored-surface, #ffffff)',
  color: activo ? 'var(--motored-brand-dark, #b00510)' : 'var(--motored-text, #1a1a18)', cursor: 'pointer',
});

function useAbiertos() {
  const [abiertos, setAbiertos] = useState([]);
  useEffect(() => {
    let vivo = true;
    listarConteos()
      .then((lista) => { if (vivo) setAbiertos((lista || []).filter((c) => ESTADOS_ABIERTOS.includes(c.estado))); })
      .catch(() => {}); // The chips are a shortcut; the panel works without them.
    return () => { vivo = false; };
  }, []);
  return abiertos;
}

export default function PanelEncabezado({ conteo, actualizado, onActualizar }) {
  const router = useRouter();
  const abiertos = useAbiertos();
  const snapshot = conteo.snapshot || {};
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-end', justifyContent: 'space-between', gap: '1rem' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', minWidth: 0 }}>
        <div style={rotuloStyle}>Conteos de inventario · Panel en vivo</div>
        <h1 style={tituloStyle}>Conteo total · {conteo.sucursal.nombre}</h1>
        <div style={{ ...mutedStyle, fontSize: '0.875rem' }}>
          {labelEstado(conteo.estado)} · Iniciado {fechaHoraBogota(conteo.iniciado_en)} · Foto del inventario cargado {fechaHoraBogota(snapshot.aplicado_en)}
          {' '}· Se actualiza cada {INTERVALO_VISIBLE_MS / 1000} s{actualizado ? ` (última ${horaBogota(new Date(actualizado))})` : ''}
        </div>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center' }}>
        {abiertos.length > 1 && (
          <div role="tablist" aria-label="Conteos abiertos" style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            {abiertos.map((c) => (
              <button
                key={c.id} type="button" role="tab" aria-selected={c.id === conteo.id} style={chip(c.id === conteo.id)}
                onClick={() => router.push(`${CONTEOS_PATH}/${c.id}`)}
              >
                {c.sucursal.nombre}
              </button>
            ))}
          </div>
        )}
        <button type="button" className="motored-btn motored-btn-secondary" style={{ minHeight: '44px' }} onClick={onActualizar}>
          Actualizar ahora
        </button>
      </div>
    </div>
  );
}
