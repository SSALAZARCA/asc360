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
 */
import { useState, useEffect, useCallback } from 'react';
import UploadMovimientoModal from './UploadMovimientoModal';
import CargasHistoryTable from './CargasHistoryTable';
import { getRolActual } from '../../../lib/motored/motoredFetch';

export default function MovimientoTab({ tipo, label }) {
  const [showUpload, setShowUpload] = useState(false);
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 className="motored-h-seccion">{label}</h2>
        {puedeSubir && (
          <button type="button" className="motored-btn motored-btn-primary" onClick={() => setShowUpload(true)}>
            Subir archivo
          </button>
        )}
      </div>

      <CargasHistoryTable refreshKey={refreshKey} tipoFijo={tipo} />

      {showUpload && (
        <UploadMovimientoModal
          tipo={tipo}
          label={label}
          onClose={() => setShowUpload(false)}
          onUploaded={handleUploaded}
        />
      )}
    </div>
  );
}
