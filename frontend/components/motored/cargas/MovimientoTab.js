'use client';
/**
 * frontend/components/motored/cargas/MovimientoTab.js
 *
 * Generic per-movement-type tab (sdd/motored-cargas-tipo-declarado; design
 * D3) -- mirrors `maestros/BulkUploadModal.js`'s `entidad`-parameterized
 * precedent: ONE component, six entries in `app/motored/maestros/page.js`'s
 * `TABS`, not six near-duplicate components. Composes an upload button ->
 * `UploadMovimientoModal` + `CargasHistoryTable` locked to this tab's own
 * `tipo` (`tipoFijo`) -- the empty state is now honest per-type (spec
 * "Empty state per tab", the original complaint this whole change fixes).
 *
 * "Subir" is hidden for `SUCURSAL`/`CONSULTA` (UI-level RBAC only -- the
 * real guarantee is server-side `require_roles("ADMIN","COMPRAS")`), same
 * criterion the retired `app/motored/cargas/page.js` used to apply.
 *
 * `CoberturaBotIndicator` (sdd/motored-ventas-perdidas-bot, Phase 7) is
 * mounted ONLY for `tipo="DEMANDA_PERDIDA"` -- Excel stays the contingency
 * path there, and this is a non-blocking visibility aid, never a gate, for
 * that tab alone.
 *
 * "Declarar sin datos" (odd/tasks/motored-cargas-sin-datos.md) sits next to
 * "Subir archivo" only on the tipos that can be declared empty
 * (`textoSinDatos`) and only for ADMIN/COMPRAS.
 */
import { useState, useEffect, useCallback } from 'react';
import UploadMovimientoModal from './UploadMovimientoModal';
import CargasHistoryTable from './CargasHistoryTable';
import CoberturaBotIndicator from './CoberturaBotIndicator';
import DeclararSinDatosModal from './DeclararSinDatosModal';
import { textoSinDatos } from './tiposCarga';
import { getRolActual } from '../../../lib/motored/motoredFetch';

export default function MovimientoTab({ tipo, label }) {
  const [showUpload, setShowUpload] = useState(false);
  const [showSinDatos, setShowSinDatos] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [puedeSubir, setPuedeSubir] = useState(false);

  useEffect(() => {
    const rol = getRolActual();
    setPuedeSubir(rol === 'ADMIN' || rol === 'COMPRAS');
  }, []);

  const handleUploaded = useCallback(() => {
    setRefreshKey((k) => k + 1);
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
        <h2 className="motored-h-seccion">{label}</h2>
        {puedeSubir && (
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {textoSinDatos(tipo) && (
              <button type="button" className="motored-btn motored-btn-secondary" onClick={() => setShowSinDatos(true)}>
                Declarar sin datos
              </button>
            )}
            <button type="button" className="motored-btn motored-btn-primary" onClick={() => setShowUpload(true)}>
              Subir archivo
            </button>
          </div>
        )}
      </div>

      {tipo === 'DEMANDA_PERDIDA' && <CoberturaBotIndicator />}

      <CargasHistoryTable refreshKey={refreshKey} tipoFijo={tipo} />

      {showUpload && (
        <UploadMovimientoModal
          tipo={tipo}
          label={label}
          onClose={() => setShowUpload(false)}
          onUploaded={handleUploaded}
        />
      )}

      {showSinDatos && (
        <DeclararSinDatosModal
          tipo={tipo}
          label={label}
          onClose={() => setShowSinDatos(false)}
          onDeclared={handleUploaded}
        />
      )}
    </div>
  );
}
