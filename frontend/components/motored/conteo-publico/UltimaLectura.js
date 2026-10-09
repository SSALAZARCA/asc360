/**
 * "Última lectura" card: the code just read, what this pair counted of it
 * here, and −/+ plus an editable quantity to correct it.
 */
import { useEffect, useState } from 'react';
import { C, MONO, tarjeta } from './estilos';
import { textoHace } from './textos';

function useAhora(ms) {
  const [ahora, setAhora] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setAhora(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return ahora;
}

const botonBase = {
  borderRadius: 12, fontWeight: 800, fontFamily: 'inherit', cursor: 'pointer', lineHeight: 1,
};

export default function UltimaLectura({ ultima, total, compacta, onAjustar }) {
  const ahora = useAhora(1000);
  const [texto, setTexto] = useState(String(total));
  const [editando, setEditando] = useState(false);

  useEffect(() => {
    if (!editando) setTexto(String(total));
  }, [total, editando]);

  if (!ultima) return null;

  const confirmar = () => {
    setEditando(false);
    const n = Number(texto);
    if (Number.isFinite(n) && n !== total) onAjustar(n);
    else setTexto(String(total));
  };

  const tamBoton = compacta ? { width: 64, height: 56, fontSize: 28 } : { width: 52, height: 52, fontSize: 26 };
  return (
    <section
      aria-label="Última lectura"
      style={{ ...tarjeta, padding: compacta ? 14 : 20, display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: compacta ? 10 : 20, borderRadius: compacta ? 14 : 12 }}
    >
      <div style={{ flex: '1 1 260px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: compacta ? 2 : 4 }}>
        <div style={{ fontSize: compacta ? 12 : 13, fontWeight: 700, color: C.ok }}>
          Última lectura · {textoHace(ultima.en, ahora)}
          {ultima.reconteoId ? ' · reconteo' : ''}
        </div>
        <div style={{ fontFamily: MONO, fontSize: compacta ? 20 : 24, fontWeight: 600, overflowWrap: 'anywhere' }}>{ultima.codigo}</div>
        {ultima.descripcion && <div style={{ fontSize: compacta ? 13 : 15, color: C.medio }}>{ultima.descripcion}</div>}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, justifyContent: 'space-between', flex: compacta ? '1 1 100%' : '0 0 auto' }}>
        <button
          type="button"
          aria-label="Restar uno"
          disabled={total <= 0}
          onClick={() => onAjustar(total - 1)}
          style={{ ...botonBase, ...tamBoton, border: `1px solid ${C.bordeCampo}`, background: C.blanco, color: C.tinta }}
        >
          −
        </button>
        <label style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, fontSize: 12, fontWeight: 700, color: C.medio }}>
          {compacta ? 'Cantidad' : 'Cantidad aquí'}
          <input
            type="number"
            min="0"
            inputMode="numeric"
            value={texto}
            onFocus={() => setEditando(true)}
            onChange={(e) => setTexto(e.target.value)}
            onBlur={confirmar}
            onKeyDown={(e) => {
              if (e.key === 'Enter') e.currentTarget.blur();
            }}
            style={{ width: compacta ? 110 : 90, height: 'auto', textAlign: 'center', fontFamily: MONO, fontSize: compacta ? 30 : 28, fontWeight: 600, padding: compacta ? 6 : 8, borderRadius: 10, border: `1px solid ${C.bordeCampo}`, color: C.tinta }}
          />
        </label>
        <button
          type="button"
          aria-label="Sumar uno"
          onClick={() => onAjustar(total + 1)}
          style={{ ...botonBase, ...tamBoton, border: 'none', background: C.tinta, color: C.blanco }}
        >
          +
        </button>
      </div>
    </section>
  );
}
