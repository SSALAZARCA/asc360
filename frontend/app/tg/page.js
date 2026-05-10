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
        // tg:// abre Telegram directamente en el dispositivo
        window.location.replace('tg://resolve?domain=SoniaUMbot&appname=asc360');
        // Fallback: si tg:// no funciona, después de 1.5s abre t.me
        setTimeout(() => {
          window.location.replace('https://t.me/SoniaUMbot/asc360');
        }, 1500);
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
            const isSuperadminWithoutTenant = data.user.role === 'superadmin' && !data.user.tenant_id;
            router.replace(isSuperadminWithoutTenant ? '/tg/tenant' : '/tg/home');
          } else {
            setError(data.detail || 'Error de autenticación.');
          }
        })
        .catch(() => setError('No se pudo conectar con el servidor.'));
    })();
  }, []);

  if (error) {
    const noTelegram = !debug?.hasTelegram;
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', gap: '1.25rem', padding: '2rem', textAlign: 'center', background: '#0a0a0c' }}>
        <img src="/logo.png" alt="UM Colombia" style={{ width: 140, objectFit: 'contain', opacity: 0.9 }} />
        {noTelegram ? (
          <>
            <p style={{ color: '#e2e2f0', fontSize: '0.9rem', fontWeight: 800, margin: 0 }}>Abrí la app desde Telegram</p>
            <p style={{ color: '#606075', fontSize: '0.75rem', margin: 0, lineHeight: 1.6 }}>
              ASC360 solo funciona dentro de Telegram.<br />Tocá el botón para abrirla correctamente.
            </p>
            <a
              href="https://t.me/SoniaUMbot/asc360"
              style={{ display: 'inline-block', marginTop: '0.5rem', padding: '0.75rem 1.75rem', background: '#ff5f33', borderRadius: 12, color: '#fff', fontWeight: 800, fontSize: '0.85rem', textDecoration: 'none' }}
            >
              Abrir en Telegram
            </a>
          </>
        ) : (
          <>
            <div style={{ width: 48, height: 48, borderRadius: 14, background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.4rem' }}>⚠</div>
            <p style={{ color: '#ef4444', fontSize: '0.85rem', fontWeight: 700, margin: 0 }}>Error</p>
            <p style={{ color: '#606075', fontSize: '0.75rem', margin: 0, lineHeight: 1.6 }}>{error}</p>
            {debug && (
              <pre style={{ color: '#3f3f55', fontSize: '0.6rem', textAlign: 'left', background: '#13131a', padding: '0.75rem', borderRadius: 8, marginTop: '0.5rem' }}>
                {JSON.stringify(debug, null, 2)}
              </pre>
            )}
          </>
        )}
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', gap: '1.5rem', background: '#0a0a0c' }}>
      <img src="/logo.png" alt="UM Colombia" style={{ width: 160, objectFit: 'contain', opacity: 0.92 }} />
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.6rem' }}>
        <div style={{ width: 28, height: 28, border: '3px solid rgba(255,95,51,0.15)', borderTopColor: '#ff5f33', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
        <p style={{ color: '#606075', fontSize: '0.7rem', margin: 0 }}>Verificando identidad...</p>
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
