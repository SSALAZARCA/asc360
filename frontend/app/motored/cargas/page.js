'use client';
/**
 * frontend/app/motored/cargas/page.js
 *
 * Cargas screen (sdd/motored-pedidos-ingesta, Phase 10, task 10.1). Un
 * drop zone compartido + una historia compartida para los 8 `tipo` de
 * `carga_archivo` -- ver `UploadCargaModal.js`/`CargasHistoryTable.js`.
 *
 * "Subir carga" queda oculto para `SUCURSAL`/`CONSULTA` (RBAC de UI, la
 * garantía real vive server-side en `require_roles("ADMIN","COMPRAS")` --
 * mismo criterio que `/motored/usuarios` restringe su botón "Crear"): la
 * spec exige que el servidor rechace, no que el botón desaparezca, pero
 * mostrar un botón que siempre falla es una mala experiencia para esos 2
 * roles de solo lectura.
 */
import { useState, useEffect, useCallback } from 'react';
import MotoredLayout from '../motored-layout';
import UploadCargaModal from '../../../components/motored/cargas/UploadCargaModal';
import CargasHistoryTable from '../../../components/motored/cargas/CargasHistoryTable';
import { getRolActual } from '../../../lib/motored/motoredFetch';

export default function CargasPage() {
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
    <MotoredLayout>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 className="motored-h-pantalla">Cargas</h1>
            <p style={{ margin: '0.35rem 0 0', fontSize: '0.8rem', color: 'var(--motored-text-muted, #5a5a5a)' }}>
              Ventas, inventario, backorder, facturas, ingresos, demanda perdida y maestros — todo
              entra por un mismo lugar.
            </p>
          </div>
          {puedeSubir && (
            <button type="button" className="motored-btn motored-btn-primary" onClick={() => setShowUpload(true)}>
              Subir carga
            </button>
          )}
        </div>

        <CargasHistoryTable refreshKey={refreshKey} />
      </div>

      {showUpload && (
        <UploadCargaModal onClose={() => setShowUpload(false)} onUploaded={handleUploaded} />
      )}
    </MotoredLayout>
  );
}
