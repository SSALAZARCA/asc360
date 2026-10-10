'use client';
import { useEffect, useState } from 'react';
import { fechaHoraBogota } from '../../../lib/motored/fechas';
import { getTrasladosHistorial } from '../../../lib/motored/gestionRepuestosApi';
import { ESTADOS_TRASLADO } from './trasladosEstilos';

const ERROR = Symbol('historial-error');
const LABEL_ESTADO = { RECIBIDO: 'Recibido', NO_HA_LLEGADO: 'Aún no llega' };
const rotulo = { margin: '0 0 8px', fontSize: '11px', fontWeight: 700, letterSpacing: '.04em', textTransform: 'uppercase' };

function Lineas({ item }) {
  return (
    <>
      <p style={{ ...rotulo, margin: '0 0 6px' }}>Referencias de {item.documento}</p>
      <ul style={{ listStyle: 'none', margin: '0 0 12px', padding: 0, display: 'flex', flexDirection: 'column', gap: '4px', whiteSpace: 'normal' }}>
        {(item.lineas || []).map((l) => (
          <li key={`${l.referencia}-${l.descripcion}`} style={{ fontSize: '12.5px', fontVariantNumeric: 'tabular-nums' }}>
            <strong>{l.referencia}</strong> · {l.descripcion} · {l.cantidad} und
          </li>
        ))}
      </ul>
    </>
  );
}

function Cambio({ h, primero }) {
  return (
    <li style={{ display: 'inline-flex', alignItems: 'center', gap: '10px' }}>
      {!primero && <span aria-hidden="true" style={{ fontWeight: 700 }}>→</span>}
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', background: '#ffffff', color: '#1a1a18', border: '1px solid #e4e4e1', borderRadius: '10px', padding: '6px 10px', fontSize: '12.5px' }}>
        <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: 999, background: ESTADOS_TRASLADO[h.estado]?.punto }} />
        <span style={{ fontVariantNumeric: 'tabular-nums' }}>{fechaHoraBogota(h.en)}</span>
        <strong>{h.por}:</strong>
        <span>{LABEL_ESTADO[h.estado] || h.estado}</span>
      </span>
    </li>
  );
}

function useHistorial(item) {
  const [lista, setLista] = useState(null);
  useEffect(() => {
    let vigente = true;
    setLista(null);
    getTrasladosHistorial(item.documento, item.bodega_salida, item.bodega_entrada)
      .then((r) => { if (vigente) setLista(r.historial || []); })
      .catch(() => { if (vigente) setLista(ERROR); });
    return () => { vigente = false; };
  }, [item.documento, item.bodega_salida, item.bodega_entrada, item.confirmado_en]);
  return lista;
}

/** The transfer's reference lines, then the chain of answers (oldest to newest; the API sends the newest first). */
export default function TrasladoHistorial({ item }) {
  const lista = useHistorial(item);
  return (
    <>
      <Lineas item={item} />
      <p style={rotulo}>Historial de {item.documento}</p>
      {lista === null && <p style={{ margin: 0, fontSize: '12.5px' }}>Cargando historial…</p>}
      {lista === ERROR && <p role="alert" style={{ margin: 0, fontSize: '12.5px' }}>No se pudo cargar el historial.</p>}
      {Array.isArray(lista) && (
        <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px 10px', whiteSpace: 'normal' }}>
          {[...lista].reverse().map((h, i) => <Cambio key={`${h.en}-${i}`} h={h} primero={i === 0} />)}
          {lista.length === 0 && <li style={{ fontSize: '12.5px' }}>Nadie ha respondido todavía.</li>}
        </ol>
      )}
    </>
  );
}
