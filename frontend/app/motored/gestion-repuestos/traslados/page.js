'use client';
/** "Traslados" (ADMIN, COMPRAS, GERENCIA, COORDINADOR_REPUESTOS and ANALISTA_ADMINISTRATIVO): pending transfers between stores. */
import MotoredLayout from '../../motored-layout';
import TrasladosContainer from '../../../../components/motored/gestion-repuestos/TrasladosContainer';

export default function TrasladosPage() {
  return (
    <MotoredLayout>
      <TrasladosContainer />
    </MotoredLayout>
  );
}
