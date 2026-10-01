'use client';
/**
 * What the ADMIN types on the Topes screen: the text of each cap field (kept
 * across searches), the changes and errors that follow from it, saving only
 * what changed in one request, and the mode switch. A failed request keeps
 * what was typed and shows the server message with its code.
 */
import { useCallback, useMemo, useState } from 'react';
import { guardarTopes, setModoTope } from '../../../lib/motored/pedidosApi';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';
import { hoyBogota } from './acciones';
import { plural } from './formato';
import { cambiosDeTopes } from './tope';

function textoGuardado(n) {
  return n > 0 ? `Se guardó el tope de ${n} ${plural(n, 'tienda', 'tiendas')}.` : 'Los topes ya tenían esos valores: no hubo nada que guardar.';
}

export default function useEdicionTopes(topes, recargar) {
  const [textos, setTextos] = useState({});
  const [guardando, setGuardando] = useState(false);
  const [aviso, setAviso] = useState('');
  const [error, setError] = useState('');
  const [cambiandoModo, setCambiandoModo] = useState(false);
  const [errorModo, setErrorModo] = useState('');
  const { cambios, errores } = useMemo(() => cambiosDeTopes(topes, textos), [topes, textos]);

  const cambiar = useCallback((id, texto) => { setAviso(''); setTextos((t) => ({ ...t, [id]: texto })); }, []);
  const descartar = useCallback(() => { setTextos({}); setError(''); }, []);

  const guardar = useCallback(async () => {
    setGuardando(true);
    setError('');
    setAviso('');
    try {
      const resultado = await guardarTopes(cambios);
      setTextos({});
      setAviso(textoGuardado(resultado.actualizados.length));
      recargar();
    } catch (fallo) {
      setError(mensajeConCodigo(fallo, 'No se pudieron guardar los topes.'));
    } finally {
      setGuardando(false);
    }
  }, [cambios, recargar]);

  const cambiarModo = useCallback(async (activo) => {
    setCambiandoModo(true);
    setErrorModo('');
    try {
      await setModoTope(activo, hoyBogota());
      recargar();
    } catch (fallo) {
      setErrorModo(mensajeConCodigo(fallo, 'No se pudo cambiar el modo tope.'));
    } finally {
      setCambiandoModo(false);
    }
  }, [recargar]);

  return { textos, cambios, errores, guardando, aviso, error, cambiandoModo, errorModo, cambiar, descartar, guardar, cambiarModo };
}
