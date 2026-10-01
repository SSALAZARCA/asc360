'use client';
/**
 * "Cantidad a pedir" of a line while the pedido is a draft: a numeric input.
 * Enter or leaving the field saves, Escape cancels, only whole numbers pass.
 * The edited dot, the Historial button and the pack warning are the same as in
 * the read-only cell (`CantidadCelda`).
 */
import { useId, useState } from 'react';
import CantidadCelda, { AvisoCantidad } from './CantidadCelda';
import { cantidadEntera, validarCantidad } from './cantidad';

const inputStyle = {
  width: '5.5rem', height: '44px', boxSizing: 'border-box', padding: '0 8px', textAlign: 'right',
  fontSize: '16px', fontWeight: 700, fontVariantNumeric: 'tabular-nums',
};

export default function CantidadEditableCell({ linea, guardando, error, onGuardar, onOlvidarError, onHistorial }) {
  const [borrador, setBorrador] = useState(null);
  const [errorLocal, setErrorLocal] = useState('');
  const idError = useId();
  const mensaje = errorLocal || error;

  const confirmar = () => {
    if (guardando || borrador === null) return;
    const { valor, error: invalido } = validarCantidad(borrador);
    if (invalido) {
      setErrorLocal(invalido);
      return;
    }
    setBorrador(null);
    onGuardar(linea, valor);
  };
  const cancelar = () => {
    setBorrador(null);
    setErrorLocal('');
    onOlvidarError(linea.id);
  };
  const alTeclear = (evento) => {
    if (evento.key === 'Enter') {
      evento.preventDefault();
      confirmar();
    } else if (evento.key === 'Escape') {
      cancelar();
    }
  };

  const entrada = (
    <input
      type="text" inputMode="numeric" autoComplete="off" style={inputStyle}
      aria-label={`Cantidad a pedir de ${linea.codigo_referencia}`}
      aria-invalid={mensaje ? 'true' : undefined} aria-describedby={mensaje ? idError : undefined}
      aria-busy={guardando ? 'true' : undefined} readOnly={Boolean(guardando)}
      value={borrador ?? cantidadEntera(linea.pedido_final)}
      onChange={(e) => { if (!guardando) { setBorrador(e.target.value); setErrorLocal(''); } }}
      onFocus={(e) => e.target.select()} onBlur={confirmar} onKeyDown={alTeclear}
    />
  );
  const aviso = <AvisoCantidad id={idError} mensaje={mensaje} />;
  return <CantidadCelda linea={linea} onHistorial={onHistorial} entrada={entrada} aviso={aviso} />;
}
