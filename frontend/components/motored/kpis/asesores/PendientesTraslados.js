'use client';
/**
 * "Traslados por recibir · tu tienda": the transfers to the asesor's store still alive in the ERP, each answered
 * "Recibido" / "No ha llegado". Same two sources as the invoices card: the public link (`enlace` = token + cédula) and
 * the staff view (only the roles `puedeConfirmarRol` accepts get the buttons). A role that cannot read it (403) sees no
 * card; any other load failure shows a short message with a retry.
 */
import { useCallback, useEffect, useState } from 'react';
import { getTrasladosAsesor, confirmarTraslado } from '../../../../lib/motored/gestionRepuestosApi';
import { verTraslados, confirmarTrasladoPublico, TRASLADOS_ERROR } from '../../../../lib/motored/informeApi';
import { getRolActual } from '../../../../lib/motored/motoredFetch';
import { COLOR } from '../tokens';
import { NUM, ROTULO, TARJETA } from '../ventas/estilos';
import { NO_HA_LLEGADO, RECIBIDO, partesTraslado, puedeConfirmarRol, quienDe, recibidos } from './pendientes';
import { PALETA, nivelPorDias } from '../../gestion-repuestos/semaforo';
import { BotonInfo, Pildora } from './PendientesUi';

const clave = (i) => `${i.documento}|${i.bodega_salida}|${i.bodega_entrada}`;
const AYUDA = 'Son los traslados hacia tu tienda que siguen vivos en el ERP según el último archivo cargado. Cuando se reciben en el ERP, desaparecen de la lista.';
const CARGANDO = 'cargando';
const FALLO = 'fallo';

/** The block of the card: `null` while loading or hidden, `FALLO` after a failed load. */
function useBloqueTraslados(data, enlace) {
  const sucursal = data?.asesor?.sucursal_id;
  // Primitives, not the `enlace` object: a parent that rebuilds the same link must not refetch.
  const token = enlace?.token;
  const cedula = enlace?.cedula;
  const [bloque, setBloque] = useState(CARGANDO);
  const [intento, setIntento] = useState(0);
  useEffect(() => {
    if (!token && !sucursal) { setBloque(null); return undefined; }
    let vigente = true;
    setBloque(CARGANDO);
    const pedir = token ? verTraslados(token, cedula) : getTrasladosAsesor(sucursal);
    pedir
      .then((b) => { if (vigente) setBloque(b); })
      .catch((e) => { if (vigente) setBloque(e.status === 403 ? null : FALLO); });
    return () => { vigente = false; };
  }, [token, cedula, sucursal, intento]);
  const reintentar = useCallback(() => setIntento((n) => n + 1), []);
  return { bloque, setBloque, reintentar };
}

function Aviso() {
  return (
    <p style={{ margin: '4px 0 0', display: 'inline-block', fontSize: 11, fontWeight: 700, color: PALETA.atencion.ink, background: PALETA.atencion.soft, border: `1px solid ${PALETA.atencion.color}`, borderRadius: 999, padding: '1px 8px' }}>
      Recíbelo en el ERP
    </p>
  );
}

function Respuestas({ item, onElegir }) {
  return (
    <span style={{ display: 'flex', gap: 6 }}>
      <Pildora texto="Recibido" color={COLOR.good} activo={item.estado === RECIBIDO} ocupada={item.guardando} onClick={() => onElegir(item, RECIBIDO)} />
      <Pildora texto="No ha llegado" color={COLOR.mid} activo={item.estado === NO_HA_LLEGADO} ocupada={item.guardando} onClick={() => onElegir(item, NO_HA_LLEGADO)} />
    </span>
  );
}

function Fila({ item, puedeConfirmar, onElegir }) {
  const { antes, dias, despues } = partesTraslado(item);
  const nivel = nivelPorDias(item.dias);
  const quien = item.guardando ? 'Guardando…' : quienDe(item);
  return (
    <li style={{ padding: '8px 0', borderBottom: `1px solid ${COLOR.wash}` }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 12px', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
          <span style={{ ...NUM, fontSize: 13, color: COLOR.ink, whiteSpace: 'nowrap' }}>{antes}<span data-nivel={nivel || undefined} style={nivel ? { color: PALETA[nivel].ink, fontWeight: 700 } : undefined}>{dias}</span>{despues}</span>
          <span style={{ fontSize: 11, color: COLOR.soft }}>Desde {item.sale}</span>
        </span>
        {puedeConfirmar && <Respuestas item={item} onElegir={onElegir} />}
      </div>
      {item.estado === RECIBIDO && <Aviso />}
      {quien && <p style={{ margin: '3px 0 0', fontSize: 11, color: COLOR.soft }}>{quien}</p>}
    </li>
  );
}

function Lista({ items, puedeConfirmar, onElegir }) {
  if (items.length === 0) return <p style={{ margin: 0, fontSize: 13.5, color: COLOR.muted, flex: '1 1 auto' }}>Sin traslados pendientes</p>;
  return (
    <>
      <p style={{ ...NUM, margin: 0, fontSize: 13.5, fontWeight: 700 }}>
        {items.length} traslados pendientes · <span style={{ color: COLOR.mid }}>{recibidos(items)} recibidos sin cargar al ERP</span>
      </p>
      <ul aria-label="Traslados pendientes" style={{ listStyle: 'none', margin: 0, padding: '0 4px 0 0', overflowY: 'auto', flex: '1 1 auto', minHeight: 0 }}>
        {items.map((i) => <Fila key={clave(i)} item={i} puedeConfirmar={puedeConfirmar} onElegir={onElegir} />)}
      </ul>
    </>
  );
}

/** Optimistic answer: the choice shows at once and goes back, with the message, if the save fails. */
function useRespuesta(enlace, setBloque) {
  const [error, setError] = useState('');
  const poner = (objetivo, cambios) => setBloque((b) => ({
    ...b, items: b.items.map((i) => (clave(i) === clave(objetivo) ? { ...i, ...cambios } : i)),
  }));
  const elegir = async (item, estado) => {
    if (item.estado === estado || item.guardando) return;
    const antes = { estado: item.estado, confirmado_por: item.confirmado_por, confirmado_en: item.confirmado_en, guardando: false };
    setError('');
    poner(item, { estado, confirmado_por: null, confirmado_en: null, guardando: true });
    try {
      const nuevo = enlace
        ? await confirmarTrasladoPublico(enlace.token, enlace.cedula, item, estado)
        : await confirmarTraslado({
          documento: item.documento, bodega_salida: item.bodega_salida, bodega_entrada: item.bodega_entrada, estado,
        });
      poner(item, { ...nuevo, guardando: false });
    } catch (e) {
      poner(item, antes);
      setError(e.message);
    }
  };
  return { error, elegir };
}

function Contenido({ bloque, reintentar, puedeConfirmar, enlace, setBloque }) {
  const { error, elegir } = useRespuesta(enlace, setBloque);
  if (bloque === FALLO) {
    return (
      <div style={{ flex: '1 1 auto' }}>
        <p style={{ margin: 0, fontSize: 13.5, color: COLOR.muted }}>{TRASLADOS_ERROR}</p>
        <button type="button" onClick={reintentar} style={{ appearance: 'none', border: 0, background: 'transparent', padding: '6px 0', fontFamily: 'inherit', fontSize: 13, fontWeight: 700, color: COLOR.info, cursor: 'pointer', textDecoration: 'underline' }}>Reintentar</button>
      </div>
    );
  }
  return (
    <>
      <Lista items={bloque.items || []} puedeConfirmar={puedeConfirmar} onElegir={elegir} />
      {error && <p role="alert" style={{ margin: 0, fontSize: 12.5, color: COLOR.bad }}>{error}</p>}
    </>
  );
}

export default function PendientesTraslados({ data, enlace }) {
  const { bloque, setBloque, reintentar } = useBloqueTraslados(data, enlace);
  const puedeConfirmar = enlace ? true : puedeConfirmarRol(getRolActual());
  if (!bloque || bloque === CARGANDO) return null;
  return (
    <section aria-label="Traslados por recibir" style={{ ...TARJETA, height: 380, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <p style={ROTULO}>Traslados por recibir · tu tienda</p>
      <Contenido bloque={bloque} reintentar={reintentar} puedeConfirmar={puedeConfirmar} enlace={enlace} setBloque={setBloque} />
      <p style={{ margin: 0, fontSize: 11, color: COLOR.soft, display: 'flex', alignItems: 'center', gap: 4 }}>
        Sale solo cuando el ERP lo recibe <BotonInfo ayuda={AYUDA} color={COLOR.soft} />
      </p>
    </section>
  );
}
