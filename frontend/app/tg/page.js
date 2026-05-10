'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getApiUrl } from '../../lib/api';

function loadTelegramScript() {
  return new Promise((resolve) => {
    if (window.Telegram?.WebApp) { resolve(); return; }
    const script = document.createElement('script');
    script.src = 'https://telegram.org/js/telegram-web-app.js';
    script.onload = resolve;
    script.onerror = resolve; // continuar aunque falle
    document.head.appendChild(script);
  });
}

export default function TgEntry() {
  const [error, setError]   = useState(null);
  const [debug, setDebug]   = useState(null);
  const router = useRouter();

  useEffect(() => {
    (async () => {
      await loadTelegramScript();

      const tg = window.Telegram?.WebApp;
      const initData = tg?.initData ?? '';

      // Debug temporal — lo quitamos una vez que funcione
      setDebug({
        hasTelegram: !!window.Telegram,
        hasWebApp:   !!tg,
        initDataLen: initData.length,
        version:     tg?.version ?? 'N/A',
      });

      if (!tg) {
        setError('window.Telegram no está disponible. Abrí desde Telegram.');
        return;
      }

      tg.ready();
      tg.expand();

      if (!initData) {
        setError('initData vacío — el bot puede necesitar un /start previo del usuario.');
        return;
      }

      fetch(`${getApiUrl()}/auth/telegram-mini-app`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ init_data: initData }),
      })
        .then(res => res.json())
        .then(data => {
          if (data.access_token) {
            sessionStorage.setItem('um_token', data.access_token);
            sessionStorage.setItem('um_user', JSON.stringify(data.user));
            router.replace('/tg/home');
          } else {
            setError(data.detail || 'Error de autenticación.');
          }
        })
        .catch(() => setError('No se pudo conectar con el servidor.'));
    })();
  }, []);

  if (error) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', gap: '1rem', padding: '2rem', textAlign: 'center' }}>
        <div style={{ width: 56, height: 56, borderRadius: 16, background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.5rem' }}>⚠</div>
        <p style={{ color: '#ef4444', fontSize: '0.85rem', fontWeight: 700, margin: 0 }}>Error</p>
        <p style={{ color: '#606075', fontSize: '0.75rem', margin: 0, lineHeight: 1.6 }}>{error}</p>
        {debug && (
          <pre style={{ color: '#3f3f55', fontSize: '0.6rem', textAlign: 'left', background: '#13131a', padding: '0.75rem', borderRadius: 8, marginTop: '0.5rem' }}>
            {JSON.stringify(debug, null, 2)}
          </pre>
        )}
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', gap: '1rem' }}>
      <div style={{ width: 36, height: 36, border: '3px solid rgba(255,95,51,0.15)', borderTopColor: '#ff5f33', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
      <p style={{ color: '#606075', fontSize: '0.75rem', margin: 0 }}>Verificando identidad...</p>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
