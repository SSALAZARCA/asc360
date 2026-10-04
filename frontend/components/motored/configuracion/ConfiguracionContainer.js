'use client';
/** Configuración page: gate, tabs by section and the body of the chosen one. ADMIN only. */
import { useState } from 'react';
import CorridaTabs from '../pedidos/CorridaTabs';
import SeccionPanel from './SeccionPanel';
import useConfiguracion from './useConfiguracion';
import useConfiguracionGate from './useConfiguracionGate';
import { SECCIONES } from './secciones';
import { errorStyle, mutedStyle } from './styles';

export default function ConfiguracionContainer() {
  const allowed = useConfiguracionGate();
  const { data, error, recargar } = useConfiguracion(allowed);
  const [activa, setActiva] = useState(SECCIONES[0].id);
  if (!allowed) return null;
  const seccion = SECCIONES.find((s) => s.id === activa);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '100%' }}>
      <h1 className="motored-h-pantalla">Configuración</h1>
      {error && <p role="alert" style={errorStyle}>{error}</p>}
      {!error && !data && <p style={mutedStyle}>Cargando...</p>}
      <CorridaTabs tabs={SECCIONES} value={activa} onChange={setActiva} />
      <SeccionPanel seccion={seccion} data={data} recargar={recargar} />
    </div>
  );
}
