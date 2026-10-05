'use client';
/**
 * "Datos actualizados a las HH:MM" under the KPI's tabs, plus the ADMIN-only note about the
 * precomputed summary and the "Recalcular" button. Everyone sees the timestamp when the summary
 * answers; the rest is for ADMIN only (the backend enforces it too).
 */
import { useEffect, useState } from 'react';
import { getRolActual } from '../../../lib/motored/motoredFetch';
import { textoActualizado, textoResumen } from './frescura';
import { COLOR } from './tokens';
import useRecalculo from './useRecalculo';

const TEXTO = { margin: 0, fontSize: 12, color: '#595954' };
const BOTON = {
  appearance: 'none', border: `1px solid ${COLOR.line}`, background: COLOR.surface, color: COLOR.ink2,
  fontFamily: 'inherit', fontSize: 12, fontWeight: 500, borderRadius: 8, padding: '6px 12px', minHeight: 32, cursor: 'pointer',
};

export default function KpiFrescura({ data, alRecalcular }) {
  const [esAdmin, setEsAdmin] = useState(false);
  useEffect(() => { setEsAdmin(getRolActual() === 'ADMIN'); }, []);
  const { estado, recalculando, error, pedir } = useRecalculo(esAdmin, alRecalcular);
  if (!data) return null;
  const ahora = new Date();
  const usando = data.usando_resumen === true;
  const principal = usando ? textoActualizado(data.datos_actualizados_en, ahora) : '';
  const nota = esAdmin && !usando ? textoResumen(estado, ahora) : '';
  if (!principal && !nota && !esAdmin) return null;
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', justifyContent: 'flex-end' }}>
      {principal && <p style={TEXTO}>{principal}</p>}
      {nota && <p style={TEXTO}>{nota}</p>}
      {recalculando && <p role="status" style={TEXTO}>Recalculando…</p>}
      {error && <p role="alert" style={{ ...TEXTO, color: 'var(--motored-danger, #C0392B)' }}>{error}</p>}
      {esAdmin && (
        <button type="button" onClick={pedir} disabled={recalculando} aria-busy={recalculando} style={{ ...BOTON, opacity: recalculando ? 0.6 : 1 }}>
          Recalcular
        </button>
      )}
    </div>
  );
}
