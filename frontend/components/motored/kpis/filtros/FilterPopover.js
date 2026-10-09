'use client';
/**
 * A header filter: label, trigger button (same size as a select) and a dialog that closes with
 * "Listo", Escape and a click outside. Which one is open is decided by the parent (one at a time).
 * A right-aligned dialog that would stick out past the left edge of the header opens toward the right
 * instead (the KPI's container clips horizontally, so it would be cut off behind the sidebar).
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { COLOR } from '../tokens';
import { BOTON_FILTRO, BOTON_LISTO, POPOVER, ROTULO_FILTRO } from './estilos';

function useCierre(abierto, onClose) {
  const ref = useRef(null);
  useEffect(() => {
    if (!abierto) return undefined;
    const fuera = (e) => { if (ref.current && !ref.current.contains(e.target)) onClose(); };
    const tecla = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('mousedown', fuera);
    document.addEventListener('keydown', tecla);
    return () => {
      document.removeEventListener('mousedown', fuera);
      document.removeEventListener('keydown', tecla);
    };
  }, [abierto, onClose]);
  return ref;
}

/** The side the dialog is anchored to: `lado`, unless anchoring it to the right would cross the header's left edge. */
function useLado(ref, abierto, lado, ancho) {
  const [efectivo, setEfectivo] = useState(lado);
  useLayoutEffect(() => {
    if (!abierto || lado !== 'right' || !ref.current) { setEfectivo(lado); return; }
    const caja = ref.current.getBoundingClientRect();
    const limite = ref.current.closest('header')?.getBoundingClientRect().left ?? 0;
    setEfectivo(caja.right - ancho < limite ? 'left' : 'right');
  }, [ref, abierto, lado, ancho]);
  return efectivo;
}

export default function FilterPopover({ rotulo, valor, dialogo, abierto, onToggle, onClose, lado = 'right', ancho = 300, resumen, acciones, children }) {
  const ref = useCierre(abierto, onClose);
  const ladoEfectivo = useLado(ref, abierto, lado, ancho);
  const boton = (
    <button type="button" aria-haspopup="dialog" aria-expanded={abierto} onClick={onToggle} style={BOTON_FILTRO}>
      <span>{valor}</span>
      <span aria-hidden="true" style={{ fontSize: 10, color: COLOR.muted }}>▼</span>
    </button>
  );
  return (
    <div ref={ref} style={ROTULO_FILTRO}>
      {rotulo}
      {acciones ? <span style={{ display: 'inline-flex', gap: 6 }}>{boton}{acciones}</span> : boton}
      {abierto && (
        <div role="dialog" aria-label={dialogo} style={{ ...POPOVER, [ladoEfectivo]: 0, width: ancho, maxWidth: '90vw', gap: 12 }}>
          {children}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: `1px solid ${COLOR.track}`, paddingTop: 10 }}>
            <span style={{ fontSize: 12, color: COLOR.muted }}>{resumen}</span>
            <button type="button" onClick={onClose} style={BOTON_LISTO}>Listo</button>
          </div>
        </div>
      )}
    </div>
  );
}
