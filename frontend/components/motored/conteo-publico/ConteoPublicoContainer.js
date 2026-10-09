'use client';

/**
 * Public pair counting page (odd/motored-conteos-inventario WU13/WU14).
 * Without a stored device session it shows the join screen; with one it
 * resumes counting. Rendered only after mount: the session lives in
 * `localStorage` and the layout depends on the window width.
 */
import { useCallback, useEffect, useState } from 'react';
import { borrarSesion, guardarSesion, leerSesionGuardada } from '../../../lib/motored/conteoPublicoApi';
import ConteoContainer from './ConteoContainer';
import IngresoContainer from './IngresoContainer';
import { C, pantalla } from './estilos';
import { TEXTOS } from './textos';

export default function ConteoPublicoContainer({ slug, intervaloEnvioMs = 1500 }) {
  const [listo, setListo] = useState(false);
  const [sesion, setSesion] = useState(null);
  const [aviso, setAviso] = useState(null);

  useEffect(() => {
    setSesion(leerSesionGuardada(slug));
    setListo(true);
  }, [slug]);

  const alIngresar = useCallback((nueva) => {
    guardarSesion(slug, nueva);
    setAviso(null);
    setSesion(nueva);
  }, [slug]);

  const terminar = useCallback((texto) => {
    borrarSesion(slug);
    setSesion(null);
    setAviso(texto);
  }, [slug]);

  const alPerderSesion = useCallback(() => terminar(TEXTOS.sesionTerminada), [terminar]);
  const alSalir = useCallback(() => terminar(TEXTOS.salida), [terminar]);

  const alCambiarUbicacion = useCallback((ubicacion) => {
    setSesion((actual) => {
      if (!actual) return actual;
      const nueva = { ...actual, ubicacion };
      guardarSesion(slug, nueva);
      return nueva;
    });
  }, [slug]);

  if (!listo) {
    return <div style={{ ...pantalla, padding: 20, color: C.medio }}>Cargando…</div>;
  }
  if (!sesion) {
    return <IngresoContainer slug={slug} aviso={aviso} onIngreso={alIngresar} />;
  }
  return (
    <ConteoContainer
      key={sesion.token}
      slug={slug}
      sesion={sesion}
      intervaloEnvioMs={intervaloEnvioMs}
      onSesionPerdida={alPerderSesion}
      onSalida={alSalir}
      onUbicacion={alCambiarUbicacion}
    />
  );
}
