'use client';
/**
 * One conteo (odd/motored-conteos-inventario, WU11/WU12). Picks the screen
 * from its estado: PROGRAMADO -> start screen ("Iniciar"); EN_CONTEO /
 * EN_RECONTEO -> live panel ("Main"), or the access screen when asked;
 * CERRADO -> result. The plain 6-digit code exists only in the answers of
 * iniciar and rotar, so it lives in memory here and is gone after a reload.
 * A test conteo (odd/tasks/motored-conteo-prueba.md) gets the PRUEBA band on
 * top of whichever screen it shows.
 */
import { useCallback, useEffect, useState } from 'react';
import { obtenerConteo, rotarCodigo } from '../../../lib/motored/conteosApi';
import { useConteosGate } from './ConteosContainer';
import { ESTADOS_ABIERTOS, permisosConteo } from './conteosFormato';
import { cardStyle, errorStyle, mutedStyle, paginaStyle, tituloStyle } from './estilos';
import IniciarVista from './IniciarVista';
import PanelVivo from './PanelVivo';
import ResultadoConteo from './ResultadoConteo';
import VolverConteos from './VolverConteos';
import AvisoPrueba from './AvisoPrueba';

function useConteo(conteoId, allowed) {
  const [conteo, setConteo] = useState(null);
  const [error, setError] = useState('');
  const cargar = useCallback(async () => {
    try {
      setConteo(await obtenerConteo(conteoId));
      setError('');
    } catch (err) {
      setError(err.message || 'No se pudo cargar el conteo.');
    }
  }, [conteoId]);
  useEffect(() => {
    if (allowed) cargar();
  }, [allowed, cargar]);
  return { conteo, setConteo, error, cargar };
}

function useCodigo(conteoId) {
  const [codigo, setCodigo] = useState('');
  const [error, setError] = useState('');
  const rotar = async () => {
    setError('');
    try {
      setCodigo((await rotarCodigo(conteoId)).codigo);
    } catch (err) {
      setError(err.message || 'No se pudo cambiar el código.');
    }
  };
  return { codigo, setCodigo, rotar, error };
}

export default function ConteoDetalleContainer({ conteoId }) {
  const allowed = useConteosGate();
  const { conteo, setConteo, error, cargar } = useConteo(conteoId, allowed);
  const acceso = useCodigo(conteoId);
  const [vista, setVista] = useState('panel');
  if (!allowed) return null;
  if (!conteo) {
    return (
      <section style={paginaStyle}>
        <VolverConteos />
        {error ? <p role="alert" style={errorStyle}>{error}</p> : <p style={mutedStyle}>Cargando conteo…</p>}
      </section>
    );
  }
  const permisos = permisosConteo();

  const alIniciar = (salida) => {
    setConteo(salida.conteo);
    acceso.setCodigo(salida.codigo);
    setVista('acceso');
  };

  const pantalla = (
    <PantallaConteo
      conteo={conteo} permisos={permisos} acceso={acceso} vista={vista} setVista={setVista}
      onIniciado={alIniciar} onCambioEstado={cargar}
    />
  );
  if (!conteo.es_prueba) return pantalla;
  return (
    <div style={paginaStyle}>
      <AvisoPrueba conteo={conteo} administra={permisos.administra} />
      {pantalla}
    </div>
  );
}

function PantallaConteo({ conteo, permisos, acceso, vista, setVista, onIniciado, onCambioEstado }) {
  if (conteo.estado === 'PROGRAMADO' || (ESTADOS_ABIERTOS.includes(conteo.estado) && vista === 'acceso')) {
    return (
      <IniciarVista
        conteo={conteo} permisos={permisos} acceso={acceso}
        onIniciado={onIniciado} onVolverPanel={() => setVista('panel')}
      />
    );
  }
  if (ESTADOS_ABIERTOS.includes(conteo.estado)) {
    return (
      <PanelVivo
        conteo={conteo} permisos={permisos} acceso={acceso}
        onVerAcceso={() => setVista('acceso')} onCambioEstado={onCambioEstado}
      />
    );
  }
  if (conteo.estado === 'CERRADO') return <ResultadoConteo conteo={conteo} />;
  return (
    <section style={paginaStyle}>
      <VolverConteos />
      <h1 style={tituloStyle}>Conteo anulado · {conteo.sucursal.nombre}</h1>
      <div style={cardStyle}>
        <p style={{ margin: 0 }}>Motivo: {conteo.motivo_anulacion || 'sin motivo registrado'}</p>
      </div>
    </section>
  );
}
