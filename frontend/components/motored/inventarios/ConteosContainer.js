'use client';
/**
 * "Inventarios > Conteos" (odd/motored-conteos-inventario, WU11): the list
 * of conteos with an estado filter. ADMIN schedules, reschedules (date and
 * leader) and annuls; the leader opens its own conteos (the backend already
 * filters them); GERENCIA reads. Gate: ADMIN, LIDER_INVENTARIOS and
 * GERENCIA only; any other role is sent to its home (UX only).
 */
import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { MOTORED_USER_KEY } from '../../../lib/motored/motoredFetch';
import { CONTEOS_PATH, CONTEOS_ROLES, homePathFor } from '../../../lib/motored/session';
import { listarConteos } from '../../../lib/motored/conteosApi';
import { permisosConteo } from './conteosFormato';
import { errorStyle, paginaStyle, rotuloStyle, tituloStyle } from './estilos';
import ConteosLista from './ConteosLista';
import ProgramarConteoDialog from './ProgramarConteoDialog';
import AnularConteoDialog from './AnularConteoDialog';

function readRole() {
  try {
    return JSON.parse(sessionStorage.getItem(MOTORED_USER_KEY))?.role ?? null;
  } catch {
    return null;
  }
}

export function useConteosGate() {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    const role = readRole();
    if (CONTEOS_ROLES.includes(role)) {
      setAllowed(true);
      return;
    }
    router.push(homePathFor(role));
  }, [router]);

  return allowed;
}

function useConteos(allowed) {
  const [estado, setEstado] = useState('');
  const [conteos, setConteos] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState('');

  const cargar = useCallback(async () => {
    setCargando(true);
    setError('');
    try {
      setConteos(await listarConteos(estado ? { estado } : {}));
    } catch (err) {
      setError(err.message || 'No se pudieron cargar los conteos.');
    } finally {
      setCargando(false);
    }
  }, [estado]);

  useEffect(() => {
    if (allowed) cargar();
  }, [allowed, cargar]);

  return { estado, setEstado, conteos, cargando, error, cargar };
}

export default function ConteosContainer() {
  const allowed = useConteosGate();
  const router = useRouter();
  const lista = useConteos(allowed);
  // { modo: 'programar' | 'reprogramar' | 'anular', conteo? }
  const [dialogo, setDialogo] = useState(null);
  if (!allowed) return null;
  const permisos = permisosConteo();

  const alTerminar = () => {
    setDialogo(null);
    lista.cargar();
  };

  return (
    <section style={paginaStyle}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
          <div style={rotuloStyle}>Inventarios</div>
          <h1 style={tituloStyle}>Conteos de inventario</h1>
        </div>
        {permisos.administra && (
          <button
            type="button" className="motored-btn motored-btn-primary" style={{ minHeight: '44px' }}
            onClick={() => setDialogo({ modo: 'programar' })}
          >
            Programar conteo
          </button>
        )}
      </div>
      {lista.error && <p role="alert" style={errorStyle}>{lista.error}</p>}
      <ConteosLista
        conteos={lista.conteos} cargando={lista.cargando} estado={lista.estado} onEstado={lista.setEstado}
        administra={permisos.administra}
        onAbrir={(conteo) => router.push(`${CONTEOS_PATH}/${conteo.id}`)}
        onReprogramar={(conteo) => setDialogo({ modo: 'reprogramar', conteo })}
        onAnular={(conteo) => setDialogo({ modo: 'anular', conteo })}
      />
      {dialogo && dialogo.modo !== 'anular' && (
        <ProgramarConteoDialog conteo={dialogo.conteo} onCancel={() => setDialogo(null)} onListo={alTerminar} />
      )}
      {dialogo?.modo === 'anular' && (
        <AnularConteoDialog conteo={dialogo.conteo} onCancel={() => setDialogo(null)} onListo={alTerminar} />
      )}
    </section>
  );
}
