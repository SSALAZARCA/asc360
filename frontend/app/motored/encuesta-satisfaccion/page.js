'use client';
/**
 * Survey admin page (ADMIN and SERVICIO_CLIENTE): public link plus
 * customer-base uploads. The backend enforces the roles; MotoredLayout only
 * keeps SERVICIO_CLIENTE inside the survey pages.
 */
import MotoredLayout from '../motored-layout';
import EncuestaAdminContainer from '../../../components/motored/encuesta-admin/EncuestaAdminContainer';

export default function EncuestaSatisfaccionPage() {
  return (
    <MotoredLayout>
      <EncuestaAdminContainer />
    </MotoredLayout>
  );
}
