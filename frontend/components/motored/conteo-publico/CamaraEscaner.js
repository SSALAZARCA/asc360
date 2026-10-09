'use client';

/**
 * Camera scanning with the browser's native `BarcodeDetector` (Chrome on
 * Android reads Code 128 / Code 39) and the back camera. Loaded lazily
 * (React.lazy) only where the API exists, so iPhone Safari and desktops
 * never download it. No dependency: where the API is missing the screen
 * offers manual entry and a Bluetooth scanner instead.
 *
 * The same code seen again within `esperaMs` is ignored, so pointing at one
 * label does not count it several times.
 */
import { useEffect, useRef, useState } from 'react';
import { C } from './estilos';

const FORMATOS = ['code_128', 'code_39', 'ean_13'];

async function crearDetector() {
  const Detector = window.BarcodeDetector;
  let formatos = FORMATOS;
  if (Detector.getSupportedFormats) {
    const soportados = await Detector.getSupportedFormats();
    formatos = FORMATOS.filter((f) => soportados.includes(f));
  }
  return new Detector(formatos.length ? { formats: formatos } : undefined);
}

export default function CamaraEscaner({ onCodigo, intervaloMs = 250, esperaMs = 1500 }) {
  const video = useRef(null);
  const callback = useRef(onCodigo);
  callback.current = onCodigo;
  const [error, setError] = useState(null);

  useEffect(() => {
    let vivo = true;
    let flujo = null;
    let temporizador = null;
    let ocupado = false;
    const ultimo = { codigo: null, en: 0 };
    const detenerFlujo = () => {
      if (flujo) flujo.getTracks().forEach((t) => t.stop());
    };
    const leer = async (detector) => {
      if (ocupado || !video.current) return;
      ocupado = true;
      try {
        const hallados = await detector.detect(video.current);
        const codigo = hallados && hallados[0] && hallados[0].rawValue;
        const ahora = Date.now();
        if (vivo && codigo && (codigo !== ultimo.codigo || ahora - ultimo.en >= esperaMs)) {
          ultimo.codigo = codigo;
          ultimo.en = ahora;
          callback.current(codigo, 'CAMARA');
        }
      } catch {
        // A frame that could not be read; the next one will.
      } finally {
        ocupado = false;
      }
    };
    (async () => {
      try {
        const detector = await crearDetector();
        flujo = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'environment' } }, audio: false,
        });
        if (!vivo) {
          detenerFlujo();
          return;
        }
        video.current.srcObject = flujo;
        await video.current.play();
        temporizador = setInterval(() => leer(detector), intervaloMs);
      } catch {
        if (vivo) setError('No se pudo abrir la cámara. Revise el permiso de cámara o escriba el código.');
      }
    })();
    return () => {
      vivo = false;
      clearInterval(temporizador);
      detenerFlujo();
    };
  }, [intervaloMs, esperaMs]);

  return (
    <div
      role="img"
      aria-label="Vista de la cámara apuntando al código de barras"
      style={{ height: 230, borderRadius: 14, background: '#27272a', position: 'relative', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
    >
      <video ref={video} muted playsInline style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
      <div style={{ position: 'relative', width: 270, maxWidth: '85%', height: 96, border: `3px solid ${C.blanco}`, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ width: '90%', height: 2, background: C.marca }} />
      </div>
      <div style={{ position: 'absolute', bottom: 12, left: 0, right: 0, textAlign: 'center', fontSize: 14, fontWeight: 700, color: C.blanco, padding: '0 12px' }}>
        {error || 'Apunte al código de barras'}
      </div>
    </div>
  );
}
