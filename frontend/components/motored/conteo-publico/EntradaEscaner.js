/**
 * The big, always-focused field of the desktop screen. A USB scanner types
 * the code in a fast burst and presses Enter or Tab (scanners come
 * configured either way); a person can type in the same
 * field. The burst speed sets the reading's metodo (ESCANER or MANUAL).
 * The focus comes back here whenever it lands on nothing or on a button,
 * and a burst typed while the focus is elsewhere is still caught.
 */
import { useEffect, useRef, useState } from 'react';
import { C, MONO } from './estilos';
import { esFinDeLectura, esRafaga, registrarTecla, useCapturaTeclado } from './teclado';

const REENFOQUE_MS = 120;

export default function EntradaEscaner({ onCodigo }) {
  const ref = useRef(null);
  const tiempos = useRef([]);
  const [valor, setValor] = useState('');

  const enfocar = () => {
    if (ref.current) ref.current.focus();
  };

  useEffect(() => {
    enfocar();
    let temporizador = null;
    const alSalirFoco = () => {
      clearTimeout(temporizador);
      temporizador = setTimeout(() => {
        const activo = document.activeElement;
        if (!activo || activo === document.body || activo.tagName === 'BUTTON') enfocar();
      }, REENFOQUE_MS);
    };
    document.addEventListener('focusout', alSalirFoco);
    return () => {
      clearTimeout(temporizador);
      document.removeEventListener('focusout', alSalirFoco);
    };
  }, []);

  useCapturaTeclado((codigo) => {
    onCodigo(codigo, 'ESCANER');
    enfocar();
  });

  const emitir = () => {
    const metodo = esRafaga(tiempos.current) ? 'ESCANER' : 'MANUAL';
    tiempos.current = [];
    const codigos = valor.split(/[\r\n\t]+/).map((c) => c.trim()).filter(Boolean);
    setValor('');
    codigos.forEach((c) => onCodigo(c, metodo));
  };

  const alTeclear = (e) => {
    // A Tab on an empty field still moves the focus as usual.
    if (esFinDeLectura(e.key) && (e.key === 'Enter' || valor.trim())) {
      e.preventDefault();
      emitir();
    } else if (e.key.length === 1) {
      if (!valor) tiempos.current = [];
      registrarTecla(tiempos.current);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <label style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 15, fontWeight: 800 }}>
        Escanee con la pistola o escriba el código
        <input
          ref={ref}
          type="text"
          value={valor}
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="characters"
          spellCheck={false}
          placeholder="Esperando lectura…"
          onChange={(e) => setValor(e.target.value)}
          onKeyDown={alTeclear}
          style={{ fontFamily: MONO, fontSize: 26, height: 'auto', padding: '18px 20px', borderRadius: 12, border: `3px solid ${C.marca}`, outline: 'none', background: C.blanco, color: C.tinta, width: '100%', boxSizing: 'border-box' }}
        />
      </label>
    </div>
  );
}
