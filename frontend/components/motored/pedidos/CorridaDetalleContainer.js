'use client';
/** Corrida detail screen: header, data age, progress (while calculating), lifecycle actions and the Tiendas table. */
import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import usePedidosGate from '../../../lib/motored/usePedidosGate';
import useTiendasCorrida from './useTiendasCorrida';
import AvisoAntiguedadBanner from './AvisoAntiguedadBanner';
import AntiguedadDatos from './AntiguedadDatos';
import EstadoCalculoBadge from './EstadoCalculoBadge';
import ProgresoCorrida from './ProgresoCorrida';
import PruebaBadge from './PruebaBadge';
import ResumenPedidosChip from './ResumenPedidosChip';
import TiendasTable from './TiendasTable';
import AccionesCorrida from './AccionesCorrida';
import AvisoPedido from './AvisoPedido';
import DialogosPedido from './DialogosPedido';
import useAccionesPedido from './useAccionesPedido';
import useSeleccionTiendas from './useSeleccionTiendas';
import useTopesCorrida from './useTopesCorrida';
import TopeResumenCorrida from './TopeResumenCorrida';
import ComparacionContainer from './ComparacionContainer';
import ConsolidadoContainer from './ConsolidadoContainer';
import CorridaTabs from './CorridaTabs';
import { estaCalculando, fechaCorta } from './reglas';
import { errorStyle, mutedStyle, volverStyle } from './styles';

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

function Cuerpo({ corrida, onOpen, ciclo, topes }) {
  if (corrida.sucursales.length === 0) {
    return <p style={mutedStyle}>{estaCalculando(corrida.estado) ? 'Calculando...' : 'Sin pedidos para mostrar'}</p>;
  }
  return <TiendasTable tiendas={corrida.sucursales} onOpen={onOpen} ciclo={ciclo} topes={topes} />;
}

const PESTANAS = [{ id: 'tiendas', label: 'Tiendas' }, { id: 'consolidado', label: 'Consolidado' }];
// Only a scenario can be compared with a real corrida.
const PESTANA_COMPARAR = { id: 'comparar', label: 'Comparar' };
const cerrada = (t) => t.estado_pedido === 'CERRADO' || t.estado_pedido === 'ENVIADO';

export default function CorridaDetalleContainer({ corridaId }) {
  const router = useRouter();
  const allowed = usePedidosGate();
  const { data, error, reload } = useTiendasCorrida(corridaId, allowed);
  const [pestana, setPestana] = useState('tiendas');
  const { marcadas, alternar, limpiar } = useSeleccionTiendas();
  // The cap summary of a real corrida (nothing for a scenario).
  const { topes, recargar: recargarTopes } = useTopesCorrida(corridaId, Boolean(allowed && data && !data.es_escenario), data && data.estado);
  // After any lifecycle change the screen reads the fresh states and forgets the ticked tiendas.
  const alCambiar = useCallback(() => { reload(); limpiar(); recargarTopes(); }, [reload, limpiar, recargarTopes]);
  const acciones = useAccionesPedido(corridaId, alCambiar);
  const abrir = useCallback((sid) => router.push(`/motored/pedidos/${corridaId}/${sid}`), [router, corridaId]);
  if (!allowed) return null;
  const seleccionadas = data ? data.sucursales.filter((t) => marcadas.has(t.sucursal_id)) : [];
  const ciclo = { alAccionar: acciones.alAccionar, ocupado: acciones.ocupado, marcadas, alternar };
  const recalcular = (fallidas) => acciones.abrir('recalcular', fallidas, { contexto: { fecha_corte: String(data.fecha_corte).slice(0, 10), codigo: data.codigo } });
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '100%' }}>
      <button type="button" className="motored-row-action" style={volverStyle} onClick={() => router.push('/motored/pedidos')}>
        ← Volver a pedidos
      </button>
      <AvisoAntiguedadBanner enabled={Boolean(allowed)} />
      {error && <p role="alert" style={errorStyle}>{error}</p>}
      {!error && !data && <p style={mutedStyle}>Cargando...</p>}
      {data && (
        <>
          <Cabecera corrida={data} onTerminal={reload} />
          <AntiguedadDatos antiguedad={data.antiguedad} advertencias={data.advertencias} />
          <CorridaTabs tabs={data.es_escenario ? [...PESTANAS, PESTANA_COMPARAR] : PESTANAS} value={pestana} onChange={setPestana} />
          {pestana === 'consolidado' && <ConsolidadoContainer corridaId={corridaId} />}
          {pestana === 'comparar' && data.es_escenario && <ComparacionContainer escenario={data} />}
          {pestana === 'tiendas' && (
            <>
              <AccionesCorrida
                corrida={data} seleccionadas={seleccionadas} ocupado={acciones.ocupado}
                onCerrar={(tiendas, todas) => acciones.abrir('cerrar', tiendas, { todas })}
                onEnviar={(tiendas) => acciones.abrir('enviar', tiendas)}
                onExportar={acciones.exportarTodas} onRecalcular={recalcular}
              />
              <AvisoPedido aviso={acciones.aviso} onDescartar={acciones.descartarAviso} onVerCorrida={(id) => router.push(`/motored/pedidos/${id}`)} />
              <TopeResumenCorrida topes={topes} />
              <Cuerpo corrida={data} onOpen={abrir} ciclo={ciclo} topes={topes} />
            </>
          )}
          <DialogosPedido acciones={acciones} corridaId={corridaId} fechaCorte={data.fecha_corte} yaCerradas={data.sucursales.filter(cerrada).length} />
        </>
      )}
    </div>
  );
}
