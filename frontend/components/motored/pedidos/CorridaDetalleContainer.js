'use client';
/** Corrida detail screen: header, data age, progress (while calculating) and the Tiendas table. */
import { useCallback } from 'react';
import { useRouter } from 'next/navigation';
import usePedidosGate from '../../../lib/motored/usePedidosGate';
import useTiendasCorrida from './useTiendasCorrida';
import AntiguedadDatos from './AntiguedadDatos';
import EstadoCalculoBadge from './EstadoCalculoBadge';
import ProgresoCorrida from './ProgresoCorrida';
import PruebaBadge from './PruebaBadge';
import ResumenPedidosChip from './ResumenPedidosChip';
import TiendasTable from './TiendasTable';
import { estaCalculando, fechaCorta } from './reglas';
import { errorStyle, mutedStyle } from './styles';

function Cabecera({ corrida, onTerminal }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <h1 className="motored-h-pantalla">{corrida.codigo}</h1>
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <EstadoCalculoBadge estado={corrida.estado} />
        {corrida.es_escenario && <PruebaBadge />}
        {corrida.invalidada && <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--motored-warning, #d97706)' }}>Datos invalidados</span>}
        <span style={mutedStyle}>Corte</span><span>{fechaCorta(corrida.fecha_corte)}</span>
        <ResumenPedidosChip pedidos={corrida.pedidos} />
      </div>
      {estaCalculando(corrida.estado) && (
        <ProgresoCorrida corridaId={corrida.id} estado={corrida.estado} onTerminal={onTerminal} />
      )}
    </div>
  );
}

function Cuerpo({ corrida, onOpen }) {
  if (corrida.sucursales.length === 0) {
    return <p style={mutedStyle}>{estaCalculando(corrida.estado) ? 'Calculando...' : 'Sin pedidos para mostrar'}</p>;
  }
  return <TiendasTable tiendas={corrida.sucursales} onOpen={onOpen} />;
}

export default function CorridaDetalleContainer({ corridaId }) {
  const router = useRouter();
  const allowed = usePedidosGate();
  const { data, error, reload } = useTiendasCorrida(corridaId, allowed);
  const abrir = useCallback((sid) => router.push(`/motored/pedidos/${corridaId}/${sid}`), [router, corridaId]);
  if (!allowed) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '100%' }}>
      <button type="button" className="motored-row-action" style={{ alignSelf: 'flex-start' }} onClick={() => router.push('/motored/pedidos')}>
        ← Volver a pedidos
      </button>
      {error && <p role="alert" style={errorStyle}>{error}</p>}
      {!error && !data && <p style={mutedStyle}>Cargando...</p>}
      {data && (
        <>
          <Cabecera corrida={data} onTerminal={reload} />
          <AntiguedadDatos antiguedad={data.antiguedad} advertencias={data.advertencias} />
          <Cuerpo corrida={data} onOpen={abrir} />
        </>
      )}
    </div>
  );
}
