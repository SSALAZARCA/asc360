'use client';
import { useEffect } from 'react';

export default function GlobalError({ error, reset }) {
  useEffect(() => {
    console.error('App error:', error);
  }, [error]);

  return (
    <div style={{
      minHeight: '100vh',
      background: '#0a0a0c',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      flexDirection: 'column',
      gap: '1.5rem',
      padding: '2rem',
    }}>
      <div style={{
        width: '56px',
        height: '56px',
        background: 'rgba(239,68,68,0.1)',
        border: '1px solid rgba(239,68,68,0.3)',
        borderRadius: '16px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: '1.5rem',
      }}>
        ⚠
      </div>
      <div style={{ textAlign: 'center' }}>
        <p style={{ color: '#fff', fontWeight: 900, fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 0.5rem' }}>
          Algo salió mal
        </p>
        <p style={{ color: '#606075', fontSize: '0.75rem', margin: 0 }}>
          Ocurrió un error inesperado en la aplicación.
        </p>
      </div>
      <button
        onClick={reset}
        style={{
          background: '#ff5f33',
          color: '#fff',
          border: 'none',
          borderRadius: '10px',
          padding: '0.65rem 1.5rem',
          fontWeight: 900,
          fontSize: '0.75rem',
          textTransform: 'uppercase',
          cursor: 'pointer',
          letterSpacing: '0.05em',
        }}
      >
        Reintentar
      </button>
    </div>
  );
}
