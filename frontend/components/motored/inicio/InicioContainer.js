'use client';
/**
 * Inicio (container): the same page for every role that reaches it. Reads
 * the session user for the greeting, loads `GET /api/motored/inicio` once
 * and hands the four figures to the boxes. The greeting never waits for
 * the request; a failed request shows every box as unavailable.
 */
import { useEffect, useMemo, useState } from 'react';
import { getInicio } from '../../../lib/motored/inicioApi';
import { MOTORED_USER_KEY } from '../../../lib/motored/motoredFetch';
import Saludo from './Saludo';
import Cifras from './Cifras';
import { figurasDe } from './figuras';

function leerUsuario() {
  try {
    return JSON.parse(sessionStorage.getItem(MOTORED_USER_KEY)) || null;
  } catch {
    return null;
  }
}

function useInicio() {
  const [estado, setEstado] = useState({ cargando: true, datos: null });
  useEffect(() => {
    let vigente = true;
    getInicio()
      .then((datos) => { if (vigente) setEstado({ cargando: false, datos }); })
      .catch(() => { if (vigente) setEstado({ cargando: false, datos: null }); });
    return () => { vigente = false; };
  }, []);
  return estado;
}

export default function InicioContainer() {
  const [usuario] = useState(leerUsuario);
  const ahora = useMemo(() => new Date(), []);
  const { cargando, datos } = useInicio();

  return (
    <div style={{ maxWidth: '1120px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <Saludo usuario={usuario} ahora={ahora} />
      <Cifras figuras={figurasDe(datos)} cargando={cargando} />
    </div>
  );
}
