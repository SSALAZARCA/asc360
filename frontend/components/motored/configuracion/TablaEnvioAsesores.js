'use client';
/**
 * "Estado del envío", per-asesor table (odd/motored-reporte-diario-asesor,
 * T3d): one row per asesor with sales, with the estado in business words
 * (and a tooltip saying what to do), the last send, and "Enviar ahora",
 * enabled only when the asesor is ready. It asks for confirmation, calls
 * POST /reporte-asesor/enviar/{usuario_id}, shows the result in the row and
 * reloads the panel. The search filters by asesor or tienda, ignoring
 * accents and case. The table scrolls inside its own box on a tablet.
 * The backend only sends the last 4 digits of the cédula.
 */
import { useMemo, useState } from 'react';
import InfoTooltip from '../InfoTooltip';
import { controlStyle, errorStyle, mutedStyle, touchStyle } from './styles';

export const ESTADOS = {
  sin_usuario: {
    etiqueta: 'Sin usuario en Lore',
    ayuda: 'Tiene ventas pero ningún usuario tiene su cédula: debe registrarse en Lore.',
  },
  cedula_pendiente: {
    etiqueta: 'Cédula pendiente',
    ayuda: 'Su usuario tiene la cédula sin aprobar: apruébela en Gestión de usuarios.',
  },
  usuario_inactivo: {
    etiqueta: 'Usuario inactivo o sin aprobar',
    ayuda: 'El usuario está desactivado o su registro no fue aprobado en Gestión de usuarios.',
  },
  sin_telegram: {
    etiqueta: 'Sin Telegram',
    ayuda: 'El usuario no tiene Telegram vinculado: debe vincularlo con Lore.',
  },
  sin_enlace: {
    etiqueta: 'Sin enlace',
    ayuda: 'No tiene enlace del informe activo: genérelo en Gestión de usuarios.',
  },
  sin_presupuesto: {
    etiqueta: 'Sin presupuesto',
    ayuda: 'Tiene ventas pero no presupuesto del mes, así que no hay informe: cárguelo en Presupuestos.',
  },
  bloqueado: {
    etiqueta: 'Bloqueó a Lore',
    ayuda: 'Telegram rechazó el último mensaje porque el asesor bloqueó el bot. Debe desbloquearlo en Telegram.',
  },
  listo: {
    etiqueta: 'Listo',
    ayuda: 'Cumple todas las condiciones: recibe el informe en el envío diario.',
  },
};

const RESULTADOS = { enviado: 'Enviado', fallido: 'Falló', bloqueado: 'Bloqueado' };

// Bogotá is UTC-5 all year (no daylight saving).
const BOGOTA_MS = 5 * 60 * 60 * 1000;
const dos = (n) => String(n).padStart(2, '0');

/** "2026-10-06T13:05:00+00:00" -> "06/10 08:05" (Bogotá time). */
export function fechaHora(iso) {
  const d = new Date(new Date(iso).getTime() - BOGOTA_MS);
  return `${dos(d.getUTCDate())}/${dos(d.getUTCMonth() + 1)} ${dos(d.getUTCHours())}:${dos(d.getUTCMinutes())}`;
}

export const normalizar = (texto) => (texto || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

function textoUltimo(ultimo) {
  if (!ultimo) return '—';
  return `${fechaHora(ultimo.en)} · ${RESULTADOS[ultimo.estado] || ultimo.estado}`;
}

const contenedorStyle = { overflowX: 'auto', maxWidth: '100%', WebkitOverflowScrolling: 'touch' };
const tablaStyle = { width: '100%', minWidth: '640px', borderCollapse: 'collapse', fontSize: '0.85rem' };
const celdaStyle = {
  padding: '0.4rem 0.5rem', textAlign: 'left', verticalAlign: 'top',
  borderBottom: '1px solid var(--motored-border, #d9d9d9)',
};
const cabeceraStyle = { ...celdaStyle, fontWeight: 600, whiteSpace: 'nowrap' };

function Accion({ fila, motivo, enviando, resultado, onPulsar }) {
  return (
    <td style={celdaStyle}>
      <span title={motivo || undefined} style={{ display: 'inline-block' }}>
        <button
          type="button" className="motored-btn motored-btn-secondary" style={{ ...touchStyle, whiteSpace: 'nowrap' }}
          disabled={Boolean(motivo) || enviando} title={motivo || undefined}
          aria-label={`Enviar ahora a ${fila.nombre}`} onClick={() => onPulsar(fila)}
        >
          {enviando ? 'Enviando…' : 'Enviar ahora'}
        </button>
      </span>
      {resultado?.texto && <p role="status" style={mutedStyle}>{resultado.texto}</p>}
      {resultado?.error && <p role="alert" style={errorStyle}>{resultado.error}</p>}
    </td>
  );
}

function FilaAsesor({ fila, faltaConfiguracion, enviando, resultado, onPulsar }) {
  const estado = ESTADOS[fila.estado] || { etiqueta: fila.estado, ayuda: '' };
  const motivo = faltaConfiguracion || (fila.puede_enviar ? '' : `${estado.etiqueta}: ${estado.ayuda}`);
  return (
    <tr>
      <td style={celdaStyle}>
        <div>{fila.nombre}</div>
        <div style={mutedStyle}>{fila.cedula_mask}</div>
      </td>
      <td style={celdaStyle}>{fila.tienda || '—'}</td>
      <td style={celdaStyle}>
        <span style={{ display: 'inline-flex', gap: '4px', alignItems: 'center' }}>
          <span>{estado.etiqueta}</span>
          {estado.ayuda && <InfoTooltip text={estado.ayuda} />}
        </span>
      </td>
      <td style={{ ...celdaStyle, whiteSpace: 'nowrap' }}>{textoUltimo(fila.ultimo_envio)}</td>
      <Accion fila={fila} motivo={motivo} enviando={enviando} resultado={resultado} onPulsar={onPulsar} />
    </tr>
  );
}

function useEnvioUno(enviar, fecha, onEnviado) {
  const [resultados, setResultados] = useState({});
  const [enviando, setEnviando] = useState(null);
  const pulsar = async (fila) => {
    if (!window.confirm(`¿Enviar ahora el informe a ${fila.nombre} por Lore?`)) return;
    setEnviando(fila.usuario_id);
    let resultado;
    try {
      const r = await enviar(fila.usuario_id, fecha ? { fecha_datos: fecha } : {});
      resultado = { texto: r.detalle, error: '' };
    } catch (err) {
      resultado = { texto: '', error: err.message || 'No se pudo enviar el informe.' };
    }
    setResultados((previos) => ({ ...previos, [fila.usuario_id]: resultado }));
    setEnviando(null);
    onEnviado();
  };
  return { resultados, enviando, pulsar };
}

export default function TablaEnvioAsesores({ filas = [], enviar, onEnviado, faltaConfiguracion, fecha }) {
  const [busqueda, setBusqueda] = useState('');
  const { resultados, enviando, pulsar } = useEnvioUno(enviar, fecha, onEnviado);
  const visibles = useMemo(() => {
    const buscado = normalizar(busqueda.trim());
    return filas.filter((f) => normalizar(`${f.nombre} ${f.tienda || ''}`).includes(buscado));
  }, [filas, busqueda]);
  if (filas.length === 0) return <p style={mutedStyle}>No hay asesores con ventas para esa fecha.</p>;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', minWidth: 0 }}>
      <label htmlFor="reporte-asesor-buscar" style={mutedStyle}>Buscar asesor o tienda</label>
      <input
        id="reporte-asesor-buscar" type="search" value={busqueda} placeholder="Nombre o tienda"
        style={{ ...controlStyle, width: '18rem' }} onChange={(e) => setBusqueda(e.target.value)}
      />
      <div style={contenedorStyle}>
        <table style={tablaStyle} aria-label="Envío por asesor">
          <thead>
            <tr>
              {['Asesor', 'Tienda', 'Estado', 'Último envío'].map((c) => <th key={c} scope="col" style={cabeceraStyle}>{c}</th>)}
              <th scope="col" style={cabeceraStyle} aria-label="Acción" />
            </tr>
          </thead>
          <tbody>
            {visibles.map((fila) => (
              <FilaAsesor
                key={fila.usuario_id || fila.cedula_mask + fila.nombre} fila={fila}
                faltaConfiguracion={faltaConfiguracion} enviando={enviando !== null && enviando === fila.usuario_id}
                resultado={fila.usuario_id ? resultados[fila.usuario_id] : null} onPulsar={pulsar}
              />
            ))}
          </tbody>
        </table>
      </div>
      {visibles.length === 0 && <p style={mutedStyle}>Ningún asesor coincide con la búsqueda.</p>}
    </div>
  );
}
