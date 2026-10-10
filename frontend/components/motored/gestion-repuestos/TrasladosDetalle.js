'use client';
import { Fragment, useState } from 'react';
import { fechaBogota, fechaHoraBogota } from '../../../lib/motored/fechas';
import { tarjeta, tituloSeccion, subtitulo, tabla, th, td, botonLink } from './ingresosEstilos';
import { ESTADOS_TRASLADO } from './trasladosEstilos';
import { nivelPorDias } from './semaforo';
import { PildoraNivel } from './SemaforoUi';
import TrasladoHistorial from './TrasladoHistorial';

const soloLectores = { position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' };

function Confirmar({ item, ocupada, onConfirmar }) {
  return (
    <td style={td(true)}>
      <button type="button" style={botonLink} disabled={ocupada} onClick={() => onConfirmar(item, 'RECIBIDO')}>Recibido</button>
      <button type="button" style={botonLink} disabled={ocupada} onClick={() => onConfirmar(item, 'NO_HA_LLEGADO')}>No ha llegado</button>
    </td>
  );
}

function Fila({ item, abierta, onAbrir, puedeConfirmar, ocupada, onConfirmar }) {
  const estado = ESTADOS_TRASLADO[item.estado] || ESTADOS_TRASLADO.SIN_CONFIRMAR;
  return (
    <Fragment>
      <tr>
        <td style={{ ...td(true), fontWeight: 700 }}>{item.documento}</td>
        <td style={td(true)}>{item.sale}</td>
        <td style={td(true)}>{item.llega || item.tienda}</td>
        <td style={td()}>{fechaBogota(item.fecha)}</td>
        <td style={td()}><PildoraNivel nivel={nivelPorDias(item.dias)}>{item.dias}</PildoraNivel></td>
        <td style={td()}>{item.refs}</td>
        <td style={td()}>{item.unidades}</td>
        <td style={td(true)}>
          <span style={{ display: 'inline-block', fontSize: '12px', fontWeight: 700, borderRadius: 999, padding: '2px 10px', whiteSpace: 'nowrap', ...estado.estilo }}>{estado.texto}</span>
        </td>
        <td style={td(true)}>{item.confirmado_por ? `${item.confirmado_por} · ${fechaHoraBogota(item.confirmado_en)}` : '—'}</td>
        {puedeConfirmar && <Confirmar item={item} ocupada={ocupada} onConfirmar={onConfirmar} />}
        <td style={td(true)}>
          <button type="button" style={botonLink} aria-expanded={abierta} onClick={onAbrir}>{abierta ? 'Ocultar' : 'Historial'}</button>
        </td>
      </tr>
      {abierta && (
        <tr>
          <td colSpan={puedeConfirmar ? 11 : 10} style={{ ...td(true), background: '#f7f7f5', color: '#1a1a18', padding: '12px 16px 14px' }}>
            <TrasladoHistorial item={item} />
          </td>
        </tr>
      )}
    </Fragment>
  );
}

function Cabecera({ puedeConfirmar }) {
  return (
    <thead>
      <tr>
        <th scope="col" style={th(true)}>Documento</th>
        <th scope="col" style={th(true)}>Sale de</th>
        <th scope="col" style={th(true)}>Llega a</th>
        <th scope="col" style={th()}>Fecha</th>
        <th scope="col" style={th()}>Días</th>
        <th scope="col" style={th()}>Refs.</th>
        <th scope="col" style={th()}>Unidades</th>
        <th scope="col" style={th(true)}>Estado</th>
        <th scope="col" style={th(true)}>Último cambio</th>
        {puedeConfirmar && <th scope="col" style={th(true)}>Confirmar</th>}
        <th scope="col" style={th(true)}><span style={soloLectores}>Historial</span></th>
      </tr>
    </thead>
  );
}

const clave = (i) => `${i.documento}|${i.bodega_salida}|${i.bodega_entrada}`;

export default function TrasladosDetalle({ items, total, puedeConfirmar, ocupada, onConfirmar }) {
  const [abierta, setAbierta] = useState(null);
  return (
    <section style={{ ...tarjeta, display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: '8px', alignItems: 'baseline' }}>
        <div>
          <h2 style={tituloSeccion}>Detalle</h2>
          <p style={subtitulo}>Traslado por traslado, el más antiguo primero · el historial muestra las referencias y quién certificó</p>
        </div>
        <span style={{ fontSize: '12.5px', fontVariantNumeric: 'tabular-nums' }}>Mostrando {items.length} de {total}</span>
      </div>
      <div style={{ overflow: 'auto', maxHeight: '560px', border: '1px solid #e4e4e1', borderRadius: '10px' }}>
        <table aria-label="Detalle" style={{ ...tabla, minWidth: puedeConfirmar ? '1180px' : '940px' }}>
          <Cabecera puedeConfirmar={puedeConfirmar} />
          <tbody>
            {items.map((item) => (
              <Fila
                key={clave(item)} item={item} abierta={abierta === clave(item)}
                onAbrir={() => setAbierta(abierta === clave(item) ? null : clave(item))}
                puedeConfirmar={puedeConfirmar} ocupada={ocupada} onConfirmar={onConfirmar}
              />
            ))}
          </tbody>
        </table>
      </div>
      {items.length === 0 && <p style={{ margin: 0, fontSize: '13px' }}>No hay traslados con estos filtros.</p>}
    </section>
  );
}
