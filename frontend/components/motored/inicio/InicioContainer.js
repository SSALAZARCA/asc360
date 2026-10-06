'use client';
/**
 * Inicio (container): reads the session user, loads `GET /api/motored/inicio`
 * once and hands plain data to the presentational blocks. The greeting and
 * "Ir a" never wait for the request; "Para hoy" shows skeletons, then the
 * cards or a Spanish error.
 */
import { useEffect, useMemo, useState } from 'react';
import { getInicio } from '../../../lib/motored/inicioApi';
import { MOTORED_USER_KEY } from '../../../lib/motored/motoredFetch';
import Saludo from './Saludo';
import ParaHoy from './ParaHoy';
import IrA from './IrA';
import EstadoDatos from './EstadoDatos';
import { accesosDe, tarjetasDe, tilesDeDatos } from './tarjetas';

const ROLES_CON_DATOS = ['ADMIN', 'COMPRAS'];

function leerUsuario() {
  try {
    return JSON.parse(sessionStorage.getItem(MOTORED_USER_KEY)) || null;
  } catch {
    return null;
  }
}

function useInicio() {
  const [estado, setEstado] = useState({ cargando: true, error: false, datos: null });
  useEffect(() => {
    let vigente = true;
    getInicio()
      .then((datos) => { if (vigente) setEstado({ cargando: false, error: false, datos }); })
      .catch(() => { if (vigente) setEstado({ cargando: false, error: true, datos: null }); });
    return () => { vigente = false; };
  }, []);
  return estado;
}

export default function InicioContainer() {
  const [usuario] = useState(leerUsuario);
  const ahora = useMemo(() => new Date(), []);
  const { cargando, error, datos } = useInicio();
  const secciones = datos?.secciones || {};
  const datosVencer = secciones.datos_por_vencer;
  const verDatos = ROLES_CON_DATOS.includes(usuario?.role) && Boolean(datosVencer);

  return (
    <div style={{ maxWidth: '1120px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '32px' }}>
      <Saludo usuario={usuario} ahora={ahora} />
      <ParaHoy tarjetas={tarjetasDe(secciones, usuario?.role)} cargando={cargando} error={error} />
      <IrA accesos={accesosDe(usuario)} />
      {verDatos && (
        <EstadoDatos disponible={datosVencer.disponible} tiles={tilesDeDatos(datosVencer.datos)} />
      )}
    </div>
  );
}
