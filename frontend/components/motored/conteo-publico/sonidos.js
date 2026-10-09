/**
 * Short Web Audio beeps (no audio files) and vibration for scan feedback.
 * Browsers start the AudioContext suspended until a user gesture; a scanner
 * key press counts, so the first beep resumes it. Every call is a no-op
 * where the APIs are missing (jsdom, old browsers).
 */
let contexto = null;

function audio() {
  if (typeof window === 'undefined') return null;
  const Ctor = window.AudioContext || window.webkitAudioContext;
  if (!Ctor) return null;
  if (!contexto) {
    try {
      contexto = new Ctor();
    } catch {
      return null;
    }
  }
  if (contexto.state === 'suspended' && contexto.resume) contexto.resume().catch(() => {});
  return contexto;
}

function tono(ctx, frecuencia, inicio, duracion, forma) {
  const osc = ctx.createOscillator();
  const ganancia = ctx.createGain();
  osc.type = forma;
  osc.frequency.value = frecuencia;
  ganancia.gain.value = 0.08;
  osc.connect(ganancia);
  ganancia.connect(ctx.destination);
  osc.start(ctx.currentTime + inicio);
  osc.stop(ctx.currentTime + inicio + duracion);
}

/** `tipo`: 'ok' (one short high beep) or 'error' (two low beeps). */
export function pitar(tipo) {
  const ctx = audio();
  if (!ctx) return;
  try {
    if (tipo === 'ok') {
      tono(ctx, 1760, 0, 0.07, 'sine');
    } else {
      tono(ctx, 220, 0, 0.18, 'square');
      tono(ctx, 180, 0.24, 0.24, 'square');
    }
  } catch {
    // Audio is a nicety; counting goes on without it.
  }
}

export function vibrar(ms = 60) {
  try {
    if (typeof navigator !== 'undefined' && navigator.vibrate) navigator.vibrate(ms);
  } catch {
    // Not supported.
  }
}
