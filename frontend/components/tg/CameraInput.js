'use client';
import { useRef, useState } from 'react';
import { authFetch } from '../../lib/authFetch';

const ENDPOINT = {
  document: '/mini-app/ai/extract-document',
  odometer: '/mini-app/ai/extract-odometer',
  part:     '/mini-app/ai/identify-part',
};

const ICON = {
  document: '🪪',
  odometer: '🔢',
  part:     '🔍',
};

/**
 * CameraInput — abre la cámara, envía la foto al endpoint AI correspondiente
 * y devuelve los datos extraídos.
 *
 * Props:
 *   mode: 'document' | 'odometer' | 'part'
 *     document → extract-document (placa, vin, marca, modelo, color…)
 *     odometer → extract-odometer (kilometraje, gasolina)
 *     part     → identify-part   (description, suggested_sections, confidence)
 *   onResult(data: object) — callback con el JSON retornado por la API
 *   onError(msg: string)   — callback opcional de error
 *   disabled?: boolean
 *   size?: number          — tamaño en px del botón (default 44)
 */
export default function CameraInput({ mode = 'document', onResult, onError, disabled = false, size = 44 }) {
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!inputRef.current) return;
    inputRef.current.value = '';           // reset para permitir re-selección
    if (!file) return;

    setLoading(true);
    const fd = new FormData();
    fd.append('image', file, file.name);

    try {
      const res = await authFetch(ENDPOINT[mode], { method: 'POST', body: fd });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      onResult?.(data);
    } catch (e) {
      onError?.(`Error al procesar imagen: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        capture="environment"
        style={{ display: 'none' }}
        onChange={handleFile}
      />
      <button
        onClick={() => !disabled && !loading && inputRef.current?.click()}
        disabled={disabled || loading}
        title={loading ? 'Procesando imagen…' : 'Tomar foto'}
        style={{
          width: size, height: size,
          borderRadius: '50%',
          border: `1.5px solid ${loading ? 'rgba(255,95,51,0.4)' : 'rgba(255,255,255,0.1)'}`,
          background: loading ? 'rgba(255,95,51,0.12)' : 'rgba(255,255,255,0.06)',
          color: loading ? '#ff5f33' : '#606075',
          fontSize: size * 0.45,
          cursor: disabled || loading ? 'not-allowed' : 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
          transition: 'all 0.15s',
          outline: 'none',
          WebkitTapHighlightColor: 'transparent',
          animation: loading ? 'tg-spin 1s linear infinite' : 'none',
        }}
      >
        {loading ? '⏳' : ICON[mode]}
        <style>{`
          @keyframes tg-spin {
            from { transform: rotate(0deg); }
            to   { transform: rotate(360deg); }
          }
        `}</style>
      </button>
    </>
  );
}
