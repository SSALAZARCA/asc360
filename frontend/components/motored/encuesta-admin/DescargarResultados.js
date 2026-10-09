'use client';
/** "Descargar resultados": Excel of every survey in a date range (by send or response date). */
import { useState } from 'react';
import InfoTooltip from '../InfoTooltip';
import { descargarResultadosEncuesta } from '../../../lib/motored/encuestaCargasApi';
import { rangoMesActual } from '../../../lib/motored/encuestaRango';
import { errorStyle } from './styles';

const POR = [['envio', 'Fecha de envío'], ['respuesta', 'Fecha de respuesta']];
const AYUDA = 'Fecha de envío: el mes del servicio (recomendado para resultados). '
  + 'Fecha de respuesta: cuándo contestó el cliente.';

const inputStyle = { padding: '6px 8px', fontSize: '13px' };
const campoStyle = { display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '12px' };

export default function DescargarResultados() {
  const [rango, setRango] = useState(() => rangoMesActual());
  const [por, setPor] = useState('envio');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const invalido = !rango.desde || !rango.hasta || rango.desde > rango.hasta;
  const ordenMal = rango.desde && rango.hasta && rango.desde > rango.hasta;

  const descargar = async () => {
    setBusy(true);
    setError('');
    try {
      await descargarResultadosEncuesta({ desde: rango.desde, hasta: rango.hasta, por });
    } catch (err) {
      setError(err.message || 'No se pudo descargar el Excel.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-end', gap: '12px' }}>
        <label style={campoStyle}>
          Desde
          <input type="date" style={inputStyle} value={rango.desde} onChange={(e) => setRango({ ...rango, desde: e.target.value })} />
        </label>
        <label style={campoStyle}>
          Hasta
          <input type="date" style={inputStyle} value={rango.hasta} onChange={(e) => setRango({ ...rango, hasta: e.target.value })} />
        </label>
        <div style={campoStyle}>
          <span>
            Filtrar por <InfoTooltip text={AYUDA} />
          </span>
          <div role="group" aria-label="Filtrar por" style={{ display: 'flex', gap: '4px' }}>
            {POR.map(([valor, texto]) => (
              <button
                key={valor}
                type="button"
                aria-pressed={por === valor}
                onClick={() => setPor(valor)}
                style={{
                  padding: '6px 10px', fontSize: '12px', cursor: 'pointer',
                  border: '1px solid var(--motored-border, #e4e4e7)', borderRadius: '6px',
                  background: por === valor ? 'var(--motored-gray-700, #595954)' : 'var(--motored-surface, #ffffff)',
                  color: por === valor ? '#ffffff' : 'inherit',
                }}
              >
                {texto}
              </button>
            ))}
          </div>
        </div>
        <button type="button" className="motored-btn" disabled={invalido || busy} onClick={descargar}>
          {busy ? 'Descargando...' : 'Descargar resultados'}
        </button>
        <InfoTooltip text="Filtra por fecha de envío de la encuesta (el mes del servicio)" />
      </div>
      {ordenMal && <p style={{ ...errorStyle }}>La fecha desde no puede ser posterior a la fecha hasta.</p>}
      {error && <div role="alert" style={errorStyle}>{error}</div>}
    </div>
  );
}
