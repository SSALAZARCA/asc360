'use client';
/** Inicio: the same welcome page for every role with screens (ADMIN, COMPRAS, GERENCIA, SERVICIO_CLIENTE). */
import MotoredLayout from '../motored-layout';
import InicioContainer from '../../../components/motored/inicio/InicioContainer';

export default function InicioPage() {
  return (
    <MotoredLayout>
      <InicioContainer />
    </MotoredLayout>
  );
}
