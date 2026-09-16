'use client';
/**
 * frontend/components/motored/maestros/SaludTab.js
 *
 * "Salud de maestros" (sdd/motored-pedidos-cimientos, proposal §7.12) --
 * lives INSIDE the same Maestros screen as a 5th tab, per the proposal's
 * own text (both the 4 CRUD tabs and the health board are described under
 * the same "§7.12 Maestros screen" section, and the real design system's
 * sidebar has a single "Maestros" entry, never a separate "Salud" one).
 *
 * Read-only: wraps `GET /maestros/salud` (`backend/app/motored/services/
 * salud.py::evaluar_salud`) exactly as the backend returns it -- `estado`
 * is "verde"/"advertencia"/"bloqueado", `hallazgos` is a flat list where
 * only `sucursal_sin_sic` is ever `bloqueante: true` (the rest are
 * warnings). This is the Fase 1 closing criterion from the proposal:
 * "tablero de salud de maestros en verde".
 */
import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import { getSalud } from '../../../lib/motored/api';

const ESTADO_INFO = {
  verde: { icon: CheckCircle2, color: 'var(--motored-success, #15803d)', bg: 'var(--motored-success-bg, #ecfdf3)', label: 'Todo en orden' },
  advertencia: { icon: AlertTriangle, color: 'var(--motored-warning, #d97706)', bg: 'var(--motored-warning-bg, #fef3e2)', label: 'Hay advertencias, nada bloqueante' },
  bloqueado: { icon: XCircle, color: 'var(--motored-danger, #c0392b)', bg: 'var(--motored-danger-bg, #fdecea)', label: 'Hay problemas bloqueantes' },
};

function EstadoBanner({ estado }) {
  const info = ESTADO_INFO[estado] || ESTADO_INFO.advertencia;
  const Icon = info.icon;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', padding: '1rem', borderRadius: 'var(--motored-radius-md, 8px)', background: info.bg }}>
      <Icon size={20} color={info.color} />
      <span style={{ fontWeight: 700, fontSize: '0.9rem', color: info.color }}>{info.label}</span>
    </div>
  );
}

function HallazgoRow({ hallazgo }) {
  const color = hallazgo.bloqueante ? 'var(--motored-danger, #c0392b)' : 'var(--motored-warning, #d97706)';
  return (
    <li style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', padding: '0.5rem 0', borderTop: '1px solid var(--motored-border, #e4e4e7)' }}>
      <span style={{ fontSize: '0.65rem', fontWeight: 700, color, textTransform: 'uppercase', flexShrink: 0 }}>
        {hallazgo.bloqueante ? 'Bloqueante' : 'Advertencia'}
      </span>
      <span style={{ fontSize: '0.8rem', color: 'var(--motored-text, #1a1a18)' }}>{hallazgo.mensaje}</span>
    </li>
  );
}

function useSalud() {
  const [salud, setSalud] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      setSalud(await getSalud());
    } catch (err) {
      setError(err.message || 'Error al cargar la salud de maestros');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { salud, loading, error, reload: load };
}

export default function SaludTab() {
  const { salud, loading, error, reload } = useSalud();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 className="motored-h-seccion">Salud de maestros</h2>
        <button type="button" className="motored-btn motored-btn-secondary" onClick={reload}>
          Actualizar
        </button>
      </div>

      {error && <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{error}</p>}

      {loading ? (
        <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>Cargando...</p>
      ) : salud && (
        <>
          <EstadoBanner estado={salud.estado} />
          {salud.hallazgos.length === 0 ? (
            <p style={{ fontSize: '0.8rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
              No hay nada que revisar — todos los maestros están completos.
            </p>
          ) : (
            <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
              {salud.hallazgos.map((h, idx) => (
                <HallazgoRow key={`${h.tipo}-${h.entidad_id || idx}`} hallazgo={h} />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
