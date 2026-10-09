'use client';
/**
 * "Pedidos por ingresar · tu tienda": the HMCL invoices of the asesor's store still waiting for an ingreso, each
 * answered "Llegó" / "No ha llegado". Two sources, same card:
 * - the public link (`enlace` = token + cédula): the block comes in the report payload and the buttons use the link;
 * - the staff view: the block is read for the asesor's sucursal and only the roles `puedeConfirmarRol` accepts (ADMIN, COORDINADOR_REPUESTOS, ANALISTA_ADMINISTRATIVO) get the buttons.
 * Nothing verifiable (no ingreso loaded, or the role cannot read it) hides the card.
 */
import { useEffect, useState } from 'react';
import { getIngresosAsesor, confirmarIngreso } from '../../../../lib/motored/gestionRepuestosApi';
import { confirmarPendiente } from '../../../../lib/motored/informeApi';
import { getRolActual } from '../../../../lib/motored/motoredFetch';
import { fechaBogota } from '../../../../lib/motored/fechas';
import { COLOR } from '../tokens';
import { NUM, ROTULO, TARJETA } from '../ventas/estilos';
import { LLEGO, NO_HA_LLEGADO, llegaron, puedeConfirmarRol, partesDe, quienDe } from './pendientes';
import { PALETA, nivelPorDias } from '../../gestion-repuestos/semaforo';

const clave = (i) => `${i.factura}|${i.sucursal_id}`;
const PILDORA = { fontFamily: 'inherit', fontSize: 11.5, fontWeight: 700, height: 26, padding: '0 10px', borderRadius: 999, cursor: 'pointer', whiteSpace: 'nowrap' };

function Pildora({ texto, color, activo, ocupada, onClick }) {
  return (
    <button
      type="button" aria-pressed={activo} disabled={ocupada} onClick={onClick}
      style={{ ...PILDORA, border: `1.5px solid ${color}`, background: activo ? color : '#FFFFFF', color: activo ? '#FFFFFF' : color }}
    >
      {texto}
    </button>
  );
}

/** Who must enter the invoice: a prominent notice for the asesor once it arrived, a muted note when the analyst does. */
function Aviso({ item }) {
  if (item.responsable === 'ANALISTA') {
    return <p style={{ margin: '3px 0 0', fontSize: 11, color: COLOR.soft }}>La ingresa el analista administrativo</p>;
  }
  if (item.responsable !== 'ASESOR' || item.estado !== LLEGO) return null;
  return (
    <p style={{ margin: '4px 0 0', display: 'inline-block', fontSize: 12, fontWeight: 700, color: PALETA.atencion.ink, background: PALETA.atencion.soft, border: `1px solid ${PALETA.atencion.color}`, borderRadius: 6, padding: '2px 8px' }}>
      Ingrésala al sistema
    </p>
  );
}

function Fila({ item, puedeConfirmar, onElegir }) {
  const { antes, dias, despues } = partesDe(item);
  const nivel = nivelPorDias(item.dias);
  const quien = item.guardando ? 'Guardando…' : quienDe(item);
  return (
    <li style={{ padding: '8px 0', borderBottom: `1px solid ${COLOR.wash}` }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 12px', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ ...NUM, fontSize: 13, color: COLOR.ink, whiteSpace: 'nowrap' }}>{antes}<span data-nivel={nivel || undefined} style={nivel ? { color: PALETA[nivel].ink, fontWeight: 700 } : undefined}>{dias}</span>{despues}</span>
        {puedeConfirmar && (
          <span style={{ display: 'flex', gap: 6 }}>
            <Pildora texto="Llegó" color={COLOR.good} activo={item.estado === LLEGO} ocupada={item.guardando} onClick={() => onElegir(item, LLEGO)} />
            <Pildora texto="No ha llegado" color={COLOR.mid} activo={item.estado === NO_HA_LLEGADO} ocupada={item.guardando} onClick={() => onElegir(item, NO_HA_LLEGADO)} />
          </span>
        )}
      </div>
      <Aviso item={item} />
      {quien && <p style={{ margin: '3px 0 0', fontSize: 11, color: COLOR.soft }}>{quien}</p>}
    </li>
  );
}

function Pie({ desde }) {
  const tip = 'Solo facturas cuya fecha está cubierta por los ingresos cargados. Cuando la factura aparece ingresada, desaparece de la lista.';
  return (
    <p style={{ margin: 0, fontSize: 11, color: COLOR.soft, display: 'flex', alignItems: 'center', gap: 4 }}>
      Verificable desde {fechaBogota(desde).slice(0, 5)} · sale sola al ingresarse
      <button type="button" aria-label="Más información" title={tip} style={{ appearance: 'none', border: 0, background: 'transparent', color: COLOR.soft, width: 18, height: 18, padding: 0, cursor: 'help', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" />
        </svg>
      </button>
    </p>
  );
}

export default function PendientesIngreso({ data, enlace }) {
  const sucursal = data?.asesor?.sucursal_id;
  const [bloque, setBloque] = useState(enlace ? data?.pendientes_ingreso || null : null);
  const [error, setError] = useState('');
  const puedeConfirmar = enlace ? true : puedeConfirmarRol(getRolActual());

  useEffect(() => {
    if (enlace || !sucursal) return undefined;
    let vigente = true;
    setBloque(null);
    getIngresosAsesor(sucursal)
      .then((b) => { if (vigente) setBloque(b); })
      .catch(() => { if (vigente) setBloque(null); }); // 403 (role cannot read it) or any failure: no card
    return () => { vigente = false; };
  }, [enlace, sucursal]);

  if (!bloque || !bloque.verificable_desde) return null;
  const items = bloque.items || [];

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
        ? await confirmarPendiente(enlace.token, enlace.cedula, item.factura, estado)
        : await confirmarIngreso({ factura: item.factura, sucursal_id: item.sucursal_id, estado });
      poner(item, { ...nuevo, guardando: false });
    } catch (e) {
      poner(item, antes);
      setError(e.message);
    }
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
      <section aria-label="Pedidos por ingresar" style={{ ...TARJETA, height: 380, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <p style={ROTULO}>Pedidos por ingresar · tu tienda</p>
        {items.length === 0 ? (
          <p style={{ margin: 0, fontSize: 13.5, color: COLOR.muted, flex: '1 1 auto' }}>No tienes facturas pendientes por ingresar.</p>
        ) : (
          <>
            <p style={{ ...NUM, margin: 0, fontSize: 13.5, fontWeight: 700 }}>
              {items.length} facturas pendientes · <span style={{ color: COLOR.mid }}>{llegaron(items)} llegaron sin ingresar</span>
            </p>
            <ul aria-label="Facturas pendientes" style={{ listStyle: 'none', margin: 0, padding: '0 4px 0 0', overflowY: 'auto', flex: '1 1 auto', minHeight: 0 }}>
              {items.map((i) => <Fila key={clave(i)} item={i} puedeConfirmar={puedeConfirmar} onElegir={elegir} />)}
            </ul>
          </>
        )}
        {error && <p role="alert" style={{ margin: 0, fontSize: 12.5, color: COLOR.bad }}>{error}</p>}
        <Pie desde={bloque.verificable_desde} />
      </section>
    </div>
  );
}
