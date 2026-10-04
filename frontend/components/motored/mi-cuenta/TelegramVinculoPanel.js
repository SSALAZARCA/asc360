'use client';
/**
 * "Mi cuenta": ADMIN and COMPRAS link their OWN Telegram to the Lore bot with
 * a one-time code (10 min) typed into the bot as `/vincular <codigo>`. The
 * early warning that pedido data is about to expire reaches COMPRAS there.
 * Other roles see nothing and nothing is requested.
 */
import { useCallback, useEffect, useState } from 'react';
import { estadoTelegram, generarCodigoTelegram, desvincularTelegram } from '../../../lib/motored/api';
import { getRolActual } from '../../../lib/motored/motoredFetch';

const ROLES = ['ADMIN', 'COMPRAS'];
const mutedStyle = { margin: 0, fontSize: '0.8rem', color: 'var(--motored-text-muted, #5a5a5a)' };

function useTelegramPropio(habilitado) {
  const [vinculado, setVinculado] = useState(null);
  const [codigo, setCodigo] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!habilitado) return undefined;
    let activo = true;
    estadoTelegram()
      .then((d) => { if (activo) setVinculado(Boolean(d.telegram_vinculado)); })
      .catch((e) => { if (activo) setError(e.message || 'No se pudo leer el estado de Telegram.'); });
    return () => { activo = false; };
  }, [habilitado]);

  const vincular = useCallback(async () => {
    setError('');
    try {
      setCodigo(await generarCodigoTelegram());
    } catch (e) {
      setError(e.message || 'No se pudo generar el código de vinculación.');
    }
  }, []);

  const desvincular = useCallback(async () => {
    setError('');
    try {
      await desvincularTelegram();
      setCodigo(null);
      setVinculado(false);
    } catch (e) {
      setError(e.message || 'No se pudo desvincular Telegram.');
    }
  }, []);

  return { vinculado, codigo, error, vincular, desvincular };
}

export default function TelegramVinculoPanel() {
  const rol = getRolActual();
  const habilitado = ROLES.includes(rol);
  const { vinculado, codigo, error, vincular, desvincular } = useTelegramPropio(habilitado);
  if (!habilitado) return null;
  return (
    <section aria-label="Telegram" style={{ marginTop: '2rem', maxWidth: '420px', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <h2 className="motored-t-interfaz" style={{ fontWeight: 700, fontSize: '1rem', margin: 0 }}>Telegram</h2>
      <p style={mutedStyle}>Vincule su Telegram para recibir los avisos de Motored en el bot Lore.</p>
      {vinculado && <p style={{ ...mutedStyle, fontWeight: 700 }}>Telegram vinculado.</p>}
      {vinculado === false && (
        <button type="button" className="motored-btn motored-btn-secondary" style={{ minHeight: '44px' }} onClick={vincular}>
          Vincular Telegram
        </button>
      )}
      {vinculado && (
        <button type="button" className="motored-btn motored-btn-secondary" style={{ minHeight: '44px' }} onClick={desvincular}>
          Desvincular Telegram
        </button>
      )}
      {codigo && (
        <p style={{ fontSize: '0.85rem', margin: 0 }}>
          Código: <strong>{codigo.codigo}</strong> (válido hasta {codigo.expira_en}). Escriba en el bot Lore: /vincular {codigo.codigo}
        </p>
      )}
      {error && <p role="alert" style={{ margin: 0, fontSize: '0.8rem', fontWeight: 700, color: 'var(--motored-danger, #c0392b)' }}>{error}</p>}
    </section>
  );
}
