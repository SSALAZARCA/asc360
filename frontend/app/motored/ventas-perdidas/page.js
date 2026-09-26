'use client';
/**
 * frontend/app/motored/ventas-perdidas/page.js
 *
 * sdd/motored-ventas-perdidas-panel, Phase 7 (design D6). Standalone
 * ADMIN-only page -- mirrors `usuarios/page.js`'s own shape (wraps
 * `MotoredLayout` around a single `*Content` component that owns the
 * ADMIN gate). Unlike `usuarios/page.js`'s own inline gate, this page uses
 * the shared `useAdminGate` hook extracted in Phase 5
 * (`lib/motored/useAdminGate.js`) -- `usuarios/page.js` itself is
 * deliberately left untouched (design D6's own accepted duplication).
 *
 * The sidebar entry (`MotoredSidebar.js`, `adminOnly: true`) ships in
 * Phase 8, not here.
 */
import MotoredLayout from '../motored-layout';
import VentasPerdidasContent from '../../../components/motored/ventas-perdidas/VentasPerdidasContent';

export default function VentasPerdidasPage() {
  return (
    <MotoredLayout>
      <VentasPerdidasContent />
    </MotoredLayout>
  );
}
