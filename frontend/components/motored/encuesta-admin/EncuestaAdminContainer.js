'use client';
import EnlaceEncuesta from './EnlaceEncuesta';
import CargaBase from './CargaBase';
import CargasRealizadas from './CargasRealizadas';
import useEncuestaAdmin from './useEncuestaAdmin';

export default function EncuestaAdminContainer() {
  const { state, actions, list } = useEncuestaAdmin();
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '100%' }}>
      <h1 className="motored-h-pantalla">Encuesta satisfacción</h1>
      <EnlaceEncuesta />
      <CargaBase state={state} actions={actions} />
      <CargasRealizadas cargas={list.cargas} loading={list.loading} error={list.error} />
    </div>
  );
}
