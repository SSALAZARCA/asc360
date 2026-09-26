'use client';
/**
 * frontend/components/motored/ventas-perdidas/VentasPerdidasContent.js
 *
 * sdd/motored-ventas-perdidas-panel, Phase 7 (design D6). Composition only:
 * ADMIN gate + filter-dropdown sources + `useVentasPerdidas` + the two
 * presentational components. Mirrors `UsuariosContent`'s division of labor
 * (gate/hooks here, rendering delegated to dumb child components).
 *
 * Dropdown sources (design D6): sucursal via `listMaestros('sucursales')`
 * (ALL rows, active or not -- Q1); asesor via `listUsuarios()` filtered to
 * `ASESOR_MOSTRADOR|ADMIN` (the only roles that can register via the bot),
 * inactive users included. Both failures degrade to an empty dropdown
 * rather than blocking the whole page -- the line list itself is the
 * primary content, not these option sources.
 */
import { useState, useEffect } from 'react';
import useAdminGate from '../../../lib/motored/useAdminGate';
import { listMaestros, listUsuarios } from '../../../lib/motored/api';
import useVentasPerdidas from './useVentasPerdidas';
import VentasPerdidasFilters from './VentasPerdidasFilters';
import VentasPerdidasTable from './VentasPerdidasTable';

const ROLES_ASESOR = ['ASESOR_MOSTRADOR', 'ADMIN'];

function useOpcionesFiltro(enabled) {
  const [sucursales, setSucursales] = useState([]);
  const [asesores, setAsesores] = useState([]);

  useEffect(() => {
    if (!enabled) return;
    listMaestros('sucursales').then(setSucursales).catch(() => setSucursales([]));
    listUsuarios()
      .then((usuarios) => setAsesores(usuarios.filter((u) => ROLES_ASESOR.includes(u.role))))
      .catch(() => setAsesores([]));
  }, [enabled]);

  return { sucursales, asesores };
}

export default function VentasPerdidasContent() {
  const { allowed } = useAdminGate();
  const { sucursales, asesores } = useOpcionesFiltro(allowed);
  const { filtros, setFiltros, lineas, loading, error, inconsistencia, editar, anular } = useVentasPerdidas(allowed);

  if (!allowed) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <h2 className="motored-h-seccion">Ventas perdidas</h2>

      <VentasPerdidasFilters filtros={filtros} setFiltros={setFiltros} sucursales={sucursales} asesores={asesores} />

      {error && <p style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>{error}</p>}
      {inconsistencia && (
        <p role="alert" style={{ color: 'var(--motored-danger, #c0392b)', fontSize: '0.8rem' }}>
          La línea se anuló, pero no se encontró el registro acumulado para revertir. Revisá manualmente.
        </p>
      )}

      {loading ? (
        <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>Cargando...</p>
      ) : lineas.length === 0 ? (
        <p style={{ color: 'var(--motored-text-muted, #5a5a5a)', fontSize: '0.8rem' }}>No hay líneas para los filtros seleccionados.</p>
      ) : (
        <VentasPerdidasTable lineas={lineas} onEditar={editar} onAnular={anular} />
      )}
    </div>
  );
}
