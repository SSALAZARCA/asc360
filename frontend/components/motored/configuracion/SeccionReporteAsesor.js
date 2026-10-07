'use client';
/**
 * Avisos tab, "Informe diario de los asesores"
 * (odd/motored-reporte-diario-asesor, T3b): the business wording of the
 * three keys (CAMPOS_REPORTE) and the "Estado del envío" panel: the last
 * send with its counts, who would get the message now, the per-asesor
 * table with "Enviar ahora" (T3d, TablaEnvioAsesores), and "Reenviar
 * reportes a todos los asesores" (asks for confirmation with the number of
 * asesores). The data date chosen here applies to both sends. The backend
 * never returns a token, a URL or a full cédula, so this screen never
 * shows them.
 */
import { useCallback, useEffect, useState } from 'react';
import InfoTooltip from '../InfoTooltip';
import TablaEnvioAsesores from './TablaEnvioAsesores';
import { enviarReporteAsesor, getReporteAsesorEstado, reenviarReportesAsesores } from '../../../lib/motored/api';
import { cardStyle, columnaStyle, controlStyle, errorStyle, filaStyle, mutedStyle, touchStyle } from './styles';

export const CLAVE_ACTIVO = 'reporte_asesor_envio_activo';

export const CAMPOS_REPORTE = [
  {
    clave: CLAVE_ACTIVO,
    etiqueta: 'Enviar cada día por Lore a cada asesor el enlace a su informe',
    ayuda: 'Encendido, Lore le manda a cada asesor, una vez por día de datos, un mensaje con su cumplimiento, '
      + 'el total estimado a pagar y su enlace personal al informe. Sale cuando ya se aplicó la carga de ventas '
      + 'que incluye el día anterior. Apagado, no se manda nada (el reenvío manual sigue disponible).',
  },
  {
    clave: 'reporte_asesor_hora_minima',
    etiqueta: 'No enviar antes de',
    ayuda: 'Hora de Bogotá. No se envía antes de esta hora, aunque los datos ya estén listos, '
      + 'para que nadie reciba mensajes de madrugada.',
  },
  {
    clave: 'reporte_asesor_hora_limite',
    etiqueta: 'Hora límite para enviar',
    ayuda: 'Hora de Bogotá. Normalmente el mensaje sale apenas el resumen de los KPI está al día. '
      + 'Si a esta hora el resumen de KPI todavía no está listo, se envía igual, calculando las cifras en vivo.',
  },
];

const AYUDA_ESTADO = 'Cómo salió el último envío y a quién le llegaría ahora. Solo reciben el mensaje los '
  + 'asesores con ventas, cédula aprobada, Telegram vinculado y enlace del informe activo '
  + '(el enlace se genera en Gestión de usuarios).';
const AYUDA_REENVIO = 'Vuelve a mandar el mensaje a todos los asesores que cumplen las condiciones, '
  + 'aunque ya lo hayan recibido (por ejemplo, después de corregir o recargar las ventas). '
  + 'Funciona aunque el envío diario esté apagado.';
const AYUDA_FECHA = 'Vacía, se usan los datos más recientes. Con una fecha, el informe dice "ventas al" esa fecha.';

/** "2026-10-06" -> "06/10/2026" (a data date, no time zone involved). */
export function fechaDatos(iso) {
  if (!iso) return '—';
  const [anio, mes, dia] = iso.split('-');
  return `${dia}/${mes}/${anio}`;
}

const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;

export function textoConteos({ enviados, fallidos, bloqueados }) {
  return [
    plural(enviados, 'enviado', 'enviados'),
    plural(fallidos, 'fallido', 'fallidos'),
    plural(bloqueados, 'bloqueado', 'bloqueados'),
  ].join(' · ');
}

function SinInforme({ estado }) {
  if (!(estado.sin_presupuesto > 0) && !(estado.sin_cedula > 0)) return null;
  return (
    <div style={columnaStyle}>
      {estado.sin_presupuesto > 0 && (
        <p style={mutedStyle}>{`${plural(estado.sin_presupuesto, 'asesor con ventas no tiene', 'asesores con ventas no tienen')} presupuesto: no tienen informe.`}</p>
      )}
      {estado.sin_cedula > 0 && (
        <p style={mutedStyle}>{`${plural(estado.sin_cedula, 'vendedor con ventas no tiene', 'vendedores con ventas no tienen')} cédula en el maestro.`}</p>
      )}
    </div>
  );
}

function Resumen({ estado }) {
  const ultimo = estado.ultimo_envio || {};
  return (
    <>
      <p style={{ margin: 0 }}>
        {ultimo.fecha_datos
          ? `Último envío: ventas al ${fechaDatos(ultimo.fecha_datos)} — ${textoConteos(ultimo)}`
          : 'Todavía no se ha enviado ningún informe.'}
      </p>
      <p style={{ margin: 0 }}>
        {estado.fecha_disponible
          ? `Datos disponibles: ventas al ${fechaDatos(estado.fecha_disponible)} · `
            + `${plural(estado.elegibles, 'asesor recibiría', 'asesores recibirían')} el mensaje.`
          : 'No hay ventas aplicadas: no hay informe para enviar.'}
      </p>
      {estado.fecha_disponible && !estado.lista_hoy && (
        <p style={mutedStyle}>Todavía no se aplicó la carga de ventas de ayer: hoy no sale el envío automático.</p>
      )}
    </>
  );
}

function useEstado(cargar) {
  const [estado, setEstado] = useState(null);
  const [error, setError] = useState('');
  const recargar = useCallback(async () => {
    try {
      setEstado(await cargar());
      setError('');
    } catch (err) {
      setError(err.message || 'No se pudo leer el estado del envío.');
    }
  }, [cargar]);
  useEffect(() => { recargar(); }, [recargar]);
  return { estado, error, recargar };
}

function Reenvio({ estado, reenviar, onEnviado, fecha, setFecha }) {
  const [aviso, setAviso] = useState({ texto: '', error: '' });
  const [enviando, setEnviando] = useState(false);
  const n = estado.elegibles || 0;
  const bloqueado = Boolean(estado.falta_configuracion) || !estado.fecha_disponible || n === 0 || enviando;
  const pulsar = async () => {
    if (!window.confirm(`Se enviará el enlace a ${n} asesores por Lore. ¿Continuar?`)) return;
    setEnviando(true);
    setAviso({ texto: '', error: '' });
    try {
      const r = await reenviar(fecha ? { fecha_datos: fecha } : {});
      setAviso({ texto: `Se están enviando ${r.a_enviar} informes (ventas al ${fechaDatos(r.fecha_datos)}).`, error: '' });
      onEnviado();
    } catch (err) {
      setAviso({ texto: '', error: err.message || 'No se pudo reenviar.' });
    } finally {
      setEnviando(false);
    }
  };
  return (
    <div style={columnaStyle}>
      <div style={{ ...filaStyle, alignItems: 'flex-end' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ display: 'inline-flex', gap: '4px', alignItems: 'center' }}>
            <label htmlFor="reporte-asesor-fecha" style={mutedStyle}>Fecha de los datos (opcional)</label>
            <InfoTooltip text={AYUDA_FECHA} />
          </span>
          <input
            id="reporte-asesor-fecha" type="date" value={fecha} max={estado.fecha_disponible || undefined}
            style={{ ...controlStyle, width: '11rem' }} onChange={(e) => setFecha(e.target.value)}
          />
        </div>
        <button type="button" className="motored-btn motored-btn-primary" style={touchStyle} disabled={bloqueado} onClick={pulsar}>
          Reenviar reportes a todos los asesores
        </button>
        <InfoTooltip text={AYUDA_REENVIO} />
      </div>
      {aviso.texto && <p role="status" style={mutedStyle}>{aviso.texto}</p>}
      {aviso.error && <p role="alert" style={errorStyle}>{aviso.error}</p>}
    </div>
  );
}

export default function PanelEnvioReporte({
  cargar = getReporteAsesorEstado, reenviar = reenviarReportesAsesores, enviarUno = enviarReporteAsesor,
}) {
  const { estado, error, recargar } = useEstado(cargar);
  const [fecha, setFecha] = useState('');
  return (
    <section style={cardStyle} aria-label="Estado del envío">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
        <h3 style={{ margin: 0, fontSize: '0.95rem' }}>Estado del envío</h3>
        <InfoTooltip text={AYUDA_ESTADO} />
      </div>
      {error && <p role="alert" style={errorStyle}>{error}</p>}
      {!estado && !error && <p style={mutedStyle}>Cargando…</p>}
      {estado && (
        <>
          {estado.falta_configuracion && <p style={errorStyle}>{estado.falta_configuracion}</p>}
          <Resumen estado={estado} />
          <SinInforme estado={estado} />
          <TablaEnvioAsesores
            filas={estado.asesores} enviar={enviarUno} onEnviado={recargar}
            faltaConfiguracion={estado.falta_configuracion} fecha={fecha}
          />
          <Reenvio estado={estado} reenviar={reenviar} onEnviado={recargar} fecha={fecha} setFecha={setFecha} />
        </>
      )}
    </section>
  );
}
