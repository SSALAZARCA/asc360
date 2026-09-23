'use client';
/**
 * frontend/components/motored/cargas/CargasHistoryTable.js
 *
 * Historia compartida de los 8 `tipo` de `carga_archivo` (sdd/motored-
 * pedidos-ingesta, Phase 10, task 10.1; spec "All eight types appear in
 * one history grid", filtrable por `tipo`/`estado`/`desde`/`hasta").
 * Visible para los 4 roles Motored (`GET /cargas` no está scopeado por
 * sucursal -- ver docstring de `backend/app/motored/api/cargas.py`,
 * "Decisión documentada -- scoping de GET /cargas").
 */
import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { listarCargas } from '../../../lib/motored/api';
import { TIPOS_CARGA, ESTADOS_CARGA, labelTipo } from './tiposCarga';
import EstadoBadge from './EstadoBadge';

const thStyle = { padding: '0 12px 8px 0', textAlign: 'left' };
const tdStyle = { padding: '10px 12px 10px 0' };

function Filtros({ filtros, setFiltros }) {
  return (
    <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Tipo
        <select value={filtros.tipo} onChange={(e) => setFiltros({ ...filtros, tipo: e.target.value })}>
          <option value="" style={{ color: '#1a1a18' }}>Todos</option>
          {TIPOS_CARGA.map((t) => (
            <option key={t.value} value={t.value} style={{ color: '#1a1a18' }}>{t.label}</option>
          ))}
        </select>
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Estado
        <select value={filtros.estado} onChange={(e) => setFiltros({ ...filtros, estado: e.target.value })}>
          <option value="" style={{ color: '#1a1a18' }}>Todos</option>
          {ESTADOS_CARGA.map((e) => (
            <option key={e} value={e} style={{ color: '#1a1a18' }}>{e}</option>
          ))}
        </select>
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Desde
        <input type="date" value={filtros.desde} onChange={(e) => setFiltros({ ...filtros, desde: e.target.value })} />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
        Hasta
        <input type="date" value={filtros.hasta} onChange={(e) => setFiltros({ ...filtros, hasta: e.target.value })} />
      </label>
    </div>
  );
}

function useCargasHistory(refreshKey) {
  const [filtros, setFiltros] = useState({ tipo: '', estado: '', desde: '', hasta: '' });
  const [cargas, setCargas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await listarCargas(filtros);
      setCargas(data);
    } catch (err) {
      setError(err.message || 'No se pudo cargar la historia de cargas');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtros.tipo, filtros.estado, filtros.desde, filtros.hasta, refreshKey]);

  useEffect(() => {
    load();
  }, [load]);

  return { filtros, setFiltros, cargas, loading, error };
}

function TablaCargas({ cargas, onFilaClick }) {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
      <thead>
        <tr style={{ color: 'var(--motored-text-muted, #5a5a5a)' }}>
          <th style={thStyle}>Archivo</th>
          <th style={thStyle}>Tipo</th>
          <th style={thStyle}>Estado</th>
          <th style={thStyle}>Período</th>
          <th style={thStyle} className="motored-mono">Filas leídas / válidas / rechazadas</th>
          <th style={thStyle}>Subida</th>
        </tr>
      </thead>
      <tbody>
        {cargas.map((carga) => (
          <tr
            key={carga.id}
            style={{ borderTop: '1px solid var(--motored-border, #e4e4e7)', cursor: 'pointer' }}
            onClick={() => onFilaClick(carga.id)}
          >
            <td style={tdStyle}>{carga.nombre_archivo}</td>
            <td style={tdStyle}>{labelTipo(carga.tipo)}</td>
            <td style={tdStyle}><EstadoBadge estado={carga.estado} size="sm" /></td>
            <td style={tdStyle} className="motored-mono">
              {carga.periodo_desde ? `${carga.periodo_desde} → ${carga.periodo_hasta}` : <em>—</em>}
            </td>
            <td style={tdStyle} className="motored-mono">
              {carga.filas_leidas} / {carga.filas_validas} / {carga.filas_rechazadas}
            </td>
            <td style={tdStyle}>{new Date(carga.created_at).toLocaleString('es-CO')}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function CargasHistoryTable({ refreshKey }) {
  const router = useRouter();
  const { filtros, setFiltros, cargas, loading, error } = useCargasHistory(refreshKey);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <Filtros filtros={filtros} setFiltros={setFiltros} />

      {error && <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{error}</p>}

      {loading ? (
        <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>Cargando...</p>
      ) : cargas.length === 0 ? (
        <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>Todavía no hay cargas.</p>
      ) : (
        <TablaCargas cargas={cargas} onFilaClick={(id) => router.push(`/motored/cargas/${id}`)} />
      )}
    </div>
  );
}
