'use client';
/**
 * One setting of the Configuración page: its label with a tooltip, the value
 * in force, a typed control, the "Rige desde" month, Guardar and the history
 * drawer. `spec` is one key of `GET /parametros/configuracion`; `etiqueta`
 * and `ayuda` are the business wording the section gives it.
 */
import { useEffect, useMemo, useState } from 'react';
import InfoTooltip from '../InfoTooltip';
import ControlValor, { esControlSimple, mensajesDe } from './controles';
import HistorialDrawer from './HistorialDrawer';
import { aBorrador, desdeBorrador, formatearValor, mesActual, vigenteDesdeDeMes } from './valor';
import { getHistorialParametro, guardarParametro } from '../../../lib/motored/configuracionApi';
import { cardStyle, controlStyle, errorStyle, filaStyle, mutedStyle, touchStyle } from './styles';

const MENSAJE_MOTOR = 'Aplica sólo a las corridas nuevas: las ya calculadas conservan su valor.';
const MENSAJE_MES = 'Un parámetro del motor sólo puede regir desde el mes en curso o uno posterior.';

function ValorActual({ spec }) {
  const { valor, fuente, vigente_desde: desde } = spec.efectivo_global;
  const texto = formatearValor(spec, valor);
  if (fuente === 'DEFAULT') return <p style={mutedStyle}>{`Valor por defecto: ${texto}`}</p>;
  return (
    <p style={mutedStyle}>
      {`Valor actual: ${texto}`}
      <span>{` · Rige desde ${desde ? desde.slice(0, 7) : '—'}`}</span>
    </p>
  );
}

function Pendientes({ spec, sucursalId }) {
  const n = spec.por_sucursal.length;
  const propios = spec.programados.filter((p) => (p.sucursal_id ?? null) === (sucursalId ?? null));
  return (
    <>
      {propios.map((p) => (
        <p key={`${p.vigente_desde}-${p.sucursal_id}`} style={mutedStyle}>
          {`Programado: ${formatearValor(spec, p.valor)} desde ${p.vigente_desde.slice(0, 7)}`}
        </p>
      ))}
      {n > 0 && <p style={mutedStyle}>{`${n} ${n === 1 ? 'tienda con valor propio' : 'tiendas con valor propio'}`}</p>}
    </>
  );
}

function Encabezado({ id, etiqueta, ayuda, simple }) {
  const Texto = simple ? 'label' : 'span';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
      <Texto {...(simple ? { htmlFor: id } : {})} className="motored-t-rotulo">{etiqueta}</Texto>
      <InfoTooltip text={ayuda} />
    </div>
  );
}

function SelectorMes({ id, valor, minimo, onChange }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
      <label htmlFor={id} style={mutedStyle}>Rige desde</label>
      <input
        id={id} type="month" value={valor} min={minimo || undefined}
        style={{ ...controlStyle, width: '11rem' }} onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

function useBorrador(spec) {
  const valor = spec.efectivo_global.valor;
  const inicial = useMemo(() => aBorrador(spec, valor), [spec, valor]);
  const [borrador, setBorrador] = useState(inicial);
  useEffect(() => setBorrador(inicial), [inicial]);
  const cambiado = JSON.stringify(borrador) !== JSON.stringify(inicial);
  return { borrador, setBorrador, cambiado };
}

export default function CampoConfiguracion({
  spec, etiqueta, ayuda, sucursalId = null, hoy = new Date(),
  onGuardar = guardarParametro, cargarHistorial = getHistorialParametro, onGuardado,
}) {
  const id = `cfg-${spec.clave}`;
  const simple = esControlSimple(spec);
  const minimo = spec.snapshotted ? mesActual(hoy) : '';
  const { borrador, setBorrador, cambiado } = useBorrador(spec);
  const [mes, setMes] = useState(mesActual(hoy));
  const [estado, setEstado] = useState({ guardando: false, error: '', aviso: '' });
  const [historial, setHistorial] = useState(false);

  const guardar = async () => {
    const { valor, error } = desdeBorrador(spec, borrador);
    const reglas = mensajesDe(spec, borrador);
    if (error || reglas.length || (minimo && mes < minimo)) {
      setEstado({ guardando: false, error: error || reglas[0] || MENSAJE_MES, aviso: '' });
      return;
    }
    setEstado({ guardando: true, error: '', aviso: '' });
    try {
      await onGuardar({ clave: spec.clave, valor, vigente_desde: vigenteDesdeDeMes(mes), sucursal_id: sucursalId });
      setEstado({ guardando: false, error: '', aviso: 'Guardado' });
      onGuardado?.();
    } catch (err) {
      setEstado({ guardando: false, error: err.message || 'No se pudo guardar.', aviso: '' });
    }
  };

  return (
    <section style={cardStyle}>
      <Encabezado id={id} etiqueta={etiqueta} ayuda={ayuda} simple={simple} />
      <ValorActual spec={spec} />
      <Pendientes spec={spec} sucursalId={sucursalId} />
      {spec.snapshotted && <p style={mutedStyle}>{MENSAJE_MOTOR}</p>}
      <div {...(simple ? {} : { role: 'group', 'aria-label': etiqueta })}>
        <ControlValor spec={spec} etiqueta={etiqueta} id={id} borrador={borrador} onChange={setBorrador} />
      </div>
      <div style={{ ...filaStyle, alignItems: 'flex-end' }}>
        <SelectorMes id={`${id}-mes`} valor={mes} minimo={minimo} onChange={setMes} />
        <button
          type="button" className="motored-btn motored-btn-primary" style={touchStyle}
          disabled={!cambiado || estado.guardando} onClick={guardar}
        >
          Guardar
        </button>
        <button type="button" className="motored-btn motored-btn-secondary" style={touchStyle} onClick={() => setHistorial(true)}>
          Ver historial
        </button>
      </div>
      {estado.aviso && <p role="status" style={mutedStyle}>{estado.aviso}</p>}
      {estado.error && <p role="alert" style={errorStyle}>{estado.error}</p>}
      {historial && (
        <HistorialDrawer spec={spec} etiqueta={etiqueta} cargar={cargarHistorial} onCerrar={() => setHistorial(false)} />
      )}
    </section>
  );
}
