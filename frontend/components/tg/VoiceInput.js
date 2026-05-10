'use client';
import { useRef, useState } from 'react';
import { authFetch } from '../../lib/authFetch';

const STATES = {
  idle:       { color: '#606075', bg: 'rgba(255,255,255,0.06)', icon: '🎙️' },
  recording:  { color: '#ef4444', bg: 'rgba(239,68,68,0.12)',   icon: '⏹' },
  processing: { color: '#ff5f33', bg: 'rgba(255,95,51,0.12)',   icon: '…' },
};

/**
 * VoiceInput — graba audio y devuelve texto transcrito por Whisper.
 *
 * Props:
 *   onTranscript(text: string) — callback con el texto final
 *   onError(msg: string)       — callback opcional de error
 *   disabled?: boolean
 *   size?: number              — tamaño en px del botón (default 44)
 */
export default function VoiceInput({ onTranscript, onError, disabled = false, size = 44 }) {
  const [phase, setPhase]     = useState('idle');   // idle | recording | processing
  const mediaRef  = useRef(null);
  const chunksRef = useRef([]);

  const start = async () => {
    if (disabled || phase !== 'idle') return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunksRef.current = [];
      const mr = new MediaRecorder(stream);
      mr.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = () => { stream.getTracks().forEach(t => t.stop()); transcribe(); };
      mediaRef.current = mr;
      mr.start();
      setPhase('recording');
    } catch {
      onError?.('No se pudo acceder al micrófono.');
    }
  };

  const stop = () => {
    if (phase !== 'recording' || !mediaRef.current) return;
    mediaRef.current.stop();
    setPhase('processing');
  };

  const transcribe = async () => {
    const mime = chunksRef.current[0]?.type || 'audio/webm';
    const blob = new Blob(chunksRef.current, { type: mime });
    const ext  = mime.includes('mp4') ? 'mp4' : mime.includes('ogg') ? 'ogg' : 'webm';

    const fd = new FormData();
    fd.append('audio', blob, `rec.${ext}`);

    try {
      const res = await authFetch('/mini-app/ai/transcribe', { method: 'POST', body: fd });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const { text } = await res.json();
      if (text?.trim()) onTranscript?.(text.trim());
      else onError?.('No se entendió el audio. Intentá de nuevo.');
    } catch (e) {
      onError?.(`Error al transcribir: ${e.message}`);
    } finally {
      setPhase('idle');
    }
  };

  const s = STATES[phase];
  const isRecording = phase === 'recording';

  return (
    <button
      onPointerDown={start}
      onPointerUp={stop}
      onPointerLeave={isRecording ? stop : undefined}
      disabled={disabled || phase === 'processing'}
      title={isRecording ? 'Soltá para enviar' : 'Mantené para grabar'}
      style={{
        width: size, height: size,
        borderRadius: '50%',
        border: `1.5px solid ${s.color}44`,
        background: s.bg,
        color: s.color,
        fontSize: size * 0.45,
        cursor: disabled ? 'not-allowed' : 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0,
        transition: 'all 0.15s',
        outline: 'none',
        WebkitTapHighlightColor: 'transparent',
        animation: isRecording ? 'tg-pulse 1s ease-in-out infinite' : 'none',
      }}
    >
      {s.icon}
      <style>{`
        @keyframes tg-pulse {
          0%, 100% { box-shadow: 0 0 0 0 rgba(239,68,68,0.4); }
          50%       { box-shadow: 0 0 0 8px rgba(239,68,68,0); }
        }
      `}</style>
    </button>
  );
}
