'use client';
/**
 * Result of a closed conteo (WU12): the accuracy KPI and money totals, the
 * forced-close reason, the result lines (largest |value| first; at most
 * MAX_FILAS drawn, the Excel has them all) and "Descargar ajustes (Excel)".
 */
import { useEffect, useState } from 'react';
import InfoTooltip from '../InfoTooltip';
import { descargarAjustes, obtenerResultado } from '../../../lib/motored/conteosApi';
import { fechaHoraBogota } from '../../../lib/motored/fechas';
import { formatEntero, formatPesos, formatPesosConSigno, formatPorcentaje } from './conteosFormato';
import { AYUDA_EXACTITUD } from './ayudas';
import ResultadoTabla from './ResultadoTabla';
import VolverConteos from './VolverConteos';
import { cardStyle, errorStyle, kpiValorStyle, mutedStyle, paginaStyle, rotuloStyle, tituloStyle } from './estilos';

function Kpi({ titulo, valor, detalle, ayuda }) {
  return (
    <div style={{ ...cardStyle, gap: '0.35rem' }}>
      <div style={{ fontSize: '0.8rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
        {titulo}{ayuda && <InfoTooltip text={ayuda} />}
      </div>
      <div style={kpiValorStyle}>{valor}</div>
      {detalle && <div style={mutedStyle}>{detalle}</div>}
    </div>
  );
}

function useResultado(conteoId) {
  const [resultado, setResultado] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let vivo = true;
    obtenerResultado(conteoId)
      .then((r) => { if (vivo) setResultado(r); })
      .catch((err) => { if (vivo) setError(err.message || 'No se pudo cargar el resultado.'); });
    return () => { vivo = false; };
  }, [conteoId]);
  return { resultado, error, setError };
}

export default function ResultadoConteo({ conteo }) {
  const { resultado, error, setError } = useResultado(conteo.id);
  const [descargando, setDescargando] = useState(false);
  const kpi = resultado?.kpi;

  const descargar = async () => {
    setDescargando(true);
    setError('');
    try {
      await descargarAjustes(conteo.id);
    } catch (err) {
      setError(err.message || 'No se pudo descargar el archivo.');
    } finally {
      setDescargando(false);
    }
  };

  return (
    <section style={paginaStyle}>
      <VolverConteos />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
          <div style={rotuloStyle}>Conteos de inventario · Cerrado {fechaHoraBogota(conteo.cerrado_en)}</div>
          <h1 style={tituloStyle}>Resultado del conteo · {conteo.sucursal.nombre}</h1>
        </div>
        <button type="button" className="motored-btn motored-btn-primary" style={{ minHeight: '48px' }} disabled={descargando} onClick={descargar}>
          Descargar ajustes (Excel)
        </button>
      </div>
      {error && <p role="alert" style={errorStyle}>{error}</p>}
      {kpi && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '0.75rem' }}>
          <Kpi
            titulo="Exactitud" ayuda={AYUDA_EXACTITUD} valor={formatPorcentaje(kpi.exactitud_pct)}
            detalle={`${formatEntero(kpi.refs_exactas)} de ${formatEntero(kpi.refs_universo)} referencias`}
          />
          <Kpi titulo="Valor del sistema" valor={formatPesos(kpi.valor_sistema)} detalle="al costo promedio de la foto" />
          <Kpi titulo="Diferencia neta" valor={formatPesosConSigno(kpi.valor_diferencia_neta)} detalle="sobrantes menos faltantes" />
          <Kpi titulo="Diferencia absoluta" valor={formatPesos(kpi.valor_diferencia_abs)} detalle="suma de todas las diferencias sin signo" />
        </div>
      )}
      {resultado?.motivo_cierre_forzado && (
        <p style={{ ...mutedStyle, margin: 0, fontSize: '0.875rem' }}>Cierre forzado. Motivo: {resultado.motivo_cierre_forzado}</p>
      )}
      {resultado && <ResultadoTabla resultado={resultado} />}
    </section>
  );
}
