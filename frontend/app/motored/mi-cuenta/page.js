'use client';
/**
 * Account page (every web role, SERVICIO_CLIENTE included): change own
 * password. Roles with no screens yet land here and read a short notice.
 */
import MotoredLayout from '../motored-layout';
import MiCuentaContainer from '../../../components/motored/mi-cuenta/MiCuentaContainer';
import { getRolActual } from '../../../lib/motored/motoredFetch';
import { ACCESO_NO_HABILITADO_NOTICE, rolSinAcceso } from '../../../lib/motored/session';

export default function MiCuentaPage() {
  const sinAcceso = rolSinAcceso(getRolActual());
  return (
    <MotoredLayout>
      {sinAcceso && (
        <div role="status" className="motored-notice-box" style={{ maxWidth: '420px', marginBottom: '1rem' }}>
          {ACCESO_NO_HABILITADO_NOTICE}
        </div>
      )}
      <MiCuentaContainer />
    </MotoredLayout>
  );
}
