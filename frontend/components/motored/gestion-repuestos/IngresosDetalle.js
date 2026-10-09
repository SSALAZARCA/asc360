'use client';
import { Fragment, useEffect, useState } from 'react';
import { formatCOP } from '../../../lib/motored/formatCOP';
import { fechaBogota, fechaHoraBogota } from '../../../lib/motored/fechas';
import { descargarPlantillaIngreso, getIngresosHistorial } from '../../../lib/motored/gestionRepuestosApi';
import {
  tarjeta, tituloSeccion, subtitulo, tabla, th, td, botonLink, ESTADOS, RESPONSABLES,
} from './ingresosEstilos';
import { PALETA, nivelEstado, nivelPorDias } from './semaforo';
import { PildoraNivel } from './SemaforoUi';

const LABEL_ESTADO = { LLEGO: 'Ya llegó', NO_HA_LLEGADO: 'Aún no llega' };

const ERROR = Symbol('historial-error');

function Historial({ item }) {
  const [lista, setLista] = useState(null);
  useEffect(() => {
    let vigente = true;
    getIngresosHistorial(item.factura, item.sucursal_id)
      .then((r) => { if (vigente) setLista(r.historial || []); })
      .catch(() => { if (vigente) setLista(ERROR); });
    return () => { vigente = false; };
  }, [item.factura, item.sucursal_id, item.confirmado_en]);
  if (lista === null) return <p style={{ margin: 0, fontSize: '12.5px' }}>Cargando historial…</p>;
  if (lista === ERROR) return <p role="alert" style={{ margin: 0, fontSize: '12.5px' }}>No se pudo cargar el historial.</p>;
  // The API sends the newest first; the design reads oldest to newest.
  const cronologico = [...lista].reverse();
  return (
    <>
      <p style={{ margin: '0 0 8px', fontSize: '11px', fontWeight: 700, letterSpacing: '.04em', textTransform: 'uppercase' }}>
        Historial de {item.factura}
      </p>
      <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px 10px', whiteSpace: 'normal' }}>
        {cronologico.map((h, i) => (
          <li key={`${h.en}-${i}`} style={{ display: 'inline-flex', alignItems: 'center', gap: '10px' }}>
            {i > 0 && <span aria-hidden="true" style={{ fontWeight: 700 }}>→</span>}
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', background: '#ffffff', color: '#1a1a18', border: '1px solid #e4e4e1', borderRadius: '10px', padding: '6px 10px', fontSize: '12.5px' }}>
              <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: 999, background: ESTADOS[h.estado]?.punto }} />
              <span style={{ fontVariantNumeric: 'tabular-nums' }}>{fechaHoraBogota(h.en)}</span>
              <strong>{h.por}:</strong>
              <span>{LABEL_ESTADO[h.estado] || h.estado}</span>
            </span>
          </li>
        ))}
        {cronologico.length === 0 && <li style={{ fontSize: '12.5px' }}>Nadie ha respondido todavía.</li>}
      </ol>
    </>
  );
}

const AYUDA_INGRESA = 'Quién ingresa la factura al ERP: el asesor de la tienda si tiene pocas referencias, o el analista administrativo si tiene muchas. El límite se define en Configuración.';

function Responsable({ responsable }) {
  const r = RESPONSABLES[responsable];
  if (!r) return '—';
  return (
    <span style={{ display: 'inline-block', fontSize: '12px', fontWeight: 700, borderRadius: 999, padding: '2px 10px', whiteSpace: 'nowrap', ...r.estilo }}>
      {r.texto}
    </span>
  );
}

function Plantilla({ item, descargando, onDescargar }) {
  if (item.puede_descargar_plantilla) {
    return (
      <button type="button" style={botonLink} disabled={descargando} onClick={() => onDescargar(item)}>
        Descargar plantilla
      </button>
    );
  }
  if (item.responsable !== 'ANALISTA' || item.estado === 'LLEGO') return null;
  return (
    <span title="La plantilla del ERP se habilita cuando se confirma que la factura llegó." style={{ fontSize: '12px', fontStyle: 'italic', color: 'var(--motored-text-muted, #595954)' }}>
      Disponible al confirmar llegada
    </span>
  );
}

function Fila({ item, abierta, onAbrir, puedeConfirmar, puedeDescargar, descargando, onDescargar, ocupada, onConfirmar }) {
  const estado = ESTADOS[item.estado] || ESTADOS.SIN_CONFIRMAR;
  const nivel = nivelEstado(item.estado, item.dias);
  const chip = nivel ? { background: PALETA[nivel].soft, color: PALETA[nivel].ink, border: `1px solid ${PALETA[nivel].color}` } : estado.estilo;
  const columnas = 11 + (puedeConfirmar ? 1 : 0);
  return (
    <Fragment>
      <tr>
        <td style={{ ...td(true), fontWeight: 700 }}>{item.factura}</td>
        <td style={td(true)}>{item.tienda}</td>
        <td style={td()}>{fechaBogota(item.fecha)}</td>
        <td style={td()}><PildoraNivel nivel={nivelPorDias(item.dias)}>{item.dias}</PildoraNivel></td>
        <td style={td()}>{item.unidades}</td>
        <td style={td()}>{item.num_referencias ?? '—'}</td>
        <td style={td(true)}><Responsable responsable={item.responsable} /></td>
        <td style={td()}>{formatCOP(item.valor)}</td>
        <td style={td(true)}>
          <span data-nivel={nivel || undefined} style={{ display: 'inline-block', fontSize: '12px', fontWeight: 700, borderRadius: 999, padding: '2px 10px', whiteSpace: 'nowrap', ...chip }}>
            {estado.texto}
          </span>
        </td>
        <td style={td(true)}>
          {item.confirmado_por ? `${item.confirmado_por} · ${fechaHoraBogota(item.confirmado_en)}` : '—'}
        </td>
        {puedeConfirmar && (
          <td style={td(true)}>
            <button type="button" style={botonLink} disabled={ocupada} onClick={() => onConfirmar(item, 'LLEGO')}>Llegó</button>
            <button type="button" style={botonLink} disabled={ocupada} onClick={() => onConfirmar(item, 'NO_HA_LLEGADO')}>No ha llegado</button>
          </td>
        )}
        <td style={td(true)}>
          {puedeDescargar && <Plantilla item={item} descargando={descargando} onDescargar={onDescargar} />}
          <button type="button" style={botonLink} aria-expanded={abierta} onClick={onAbrir}>
            {abierta ? 'Ocultar' : 'Historial'}
          </button>
        </td>
      </tr>
      {abierta && (
        <tr>
          <td colSpan={columnas} style={{ ...td(true), background: '#f7f7f5', color: '#1a1a18', padding: '12px 16px 14px' }}>
            <Historial item={item} />
          </td>
        </tr>
      )}
    </Fragment>
  );
}

/** The template download in flight and the backend's message when it fails. */
function useDescargaPlantilla() {
  const [descargando, setDescargando] = useState(false);
  const [errorDescarga, setErrorDescarga] = useState('');
  const descargar = async (item) => {
    setErrorDescarga('');
    setDescargando(true);
    try {
      await descargarPlantillaIngreso(item.factura, item.sucursal_id);
    } catch (e) {
      setErrorDescarga(e.message || 'No se pudo descargar la plantilla.');
    } finally {
      setDescargando(false);
    }
  };
  return { descargando, errorDescarga, descargar };
}

export default function IngresosDetalle({ items, total, puedeConfirmar, puedeDescargar = false, ocupada, onConfirmar, cargando }) {
  const [abierta, setAbierta] = useState(null);
  const { descargando, errorDescarga, descargar } = useDescargaPlantilla();
  const clave = (i) => `${i.factura}|${i.sucursal_id}`;
  return (
    <section style={{ ...tarjeta, display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: '8px', alignItems: 'baseline' }}>
        <div>
          <h2 style={tituloSeccion}>Detalle</h2>
          <p style={subtitulo}>Factura por factura, la más antigua primero</p>
        </div>
        <span style={{ fontSize: '12.5px', fontVariantNumeric: 'tabular-nums' }}>
          Mostrando {items.length} de {total}
        </span>
      </div>
      <div style={{ overflow: 'auto', maxHeight: '560px', border: '1px solid #e4e4e1', borderRadius: '10px', opacity: cargando ? 0.6 : 1 }}>
        <table aria-label="Detalle" style={{ ...tabla, minWidth: puedeConfirmar ? '1300px' : '1140px' }}>
          <thead>
            <tr>
              <th scope="col" style={th(true)}>Factura</th>
              <th scope="col" style={th(true)}>Tienda</th>
              <th scope="col" style={th()}>Fecha</th>
              <th scope="col" style={th()}>Días</th>
              <th scope="col" style={th()}>Unidades</th>
              <th scope="col" style={th()}>Refs.</th>
              <th scope="col" style={th(true)} title={AYUDA_INGRESA}>Ingresa</th>
              <th scope="col" style={th()}>Valor</th>
              <th scope="col" style={th(true)}>Estado</th>
              <th scope="col" style={th(true)}>Último cambio</th>
              {puedeConfirmar && <th scope="col" style={th(true)}>Confirmar</th>}
              <th scope="col" style={th(true)}><span className="sr-only" style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}>Historial</span></th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <Fila
                key={clave(item)} item={item} abierta={abierta === clave(item)}
                onAbrir={() => setAbierta(abierta === clave(item) ? null : clave(item))}
                puedeConfirmar={puedeConfirmar} puedeDescargar={puedeDescargar} descargando={descargando}
                onDescargar={descargar} ocupada={ocupada} onConfirmar={onConfirmar}
              />
            ))}
          </tbody>
        </table>
      </div>
      {errorDescarga && <p role="alert" style={{ margin: 0, fontSize: '13px', color: 'var(--motored-danger, #c0392b)' }}>{errorDescarga}</p>}
      {items.length === 0 && !cargando && (
        <p style={{ margin: 0, fontSize: '13px' }}>No hay facturas con estos filtros.</p>
      )}
    </section>
  );
}
