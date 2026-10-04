'use client';
/** Corridas screen: launch form + filters + table + paging + anular dialog, the way into Topes por tienda and, for ADMIN, the scenario launcher. */
import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import usePedidosGate from '../../../lib/motored/usePedidosGate';
import { getRolActual } from '../../../lib/motored/motoredFetch';
import { ACTION_ICONS } from '../actionIcons';
import { aPagina } from '../../../lib/motored/paginacion';
import DetractoresPagination from '../detractores/DetractoresPagination';
import useCorridas from './useCorridas';
import useLanzarCorrida from './useLanzarCorrida';
import useAnularCorrida from './useAnularCorrida';
import AvisoAntiguedadBanner from './AvisoAntiguedadBanner';
import LanzarCorridaForm from './LanzarCorridaForm';
import CorridasFiltros from './CorridasFiltros';
import CorridasTable from './CorridasTable';
import AnularCorridaDialog from './AnularCorridaDialog';
import EscenarioDialog from './EscenarioDialog';
import { errorStyle, mutedStyle } from './styles';

function Cuerpo({ list, onOpen, onAnular }) {
  const { data, loading, error, filters, setPage } = list;
  if (error) return <p role="alert" style={errorStyle}>{error}</p>;
  if (!data) return <p style={mutedStyle}>Cargando...</p>;
  if (data.items.length === 0) {
    return <p style={mutedStyle}>{loading ? 'Cargando...' : 'Sin pedidos para mostrar'}</p>;
  }
  const { pageSize, total } = aPagina(data);
  return (
    <>
      <CorridasTable corridas={data.items} onOpen={onOpen} onAnular={onAnular} onTerminal={list.reload} />
      <DetractoresPagination touch page={filters.page} pageSize={pageSize} total={total} onChange={setPage} />
    </>
  );
}

function AvisoEscenario({ escenario, onVer }) {
  return (
    <div role="status" style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap', fontSize: '0.85rem', fontWeight: 600 }}>
      <span>{`Escenario ${escenario.codigo} creado: se está calculando.`}</span>
      <button type="button" className="motored-btn motored-btn-secondary" style={{ minHeight: '44px' }} onClick={() => onVer(escenario.id)}>
        Ver escenario
      </button>
    </div>
  );
}

export default function CorridasContainer() {
  const router = useRouter();
  const allowed = usePedidosGate();
  const list = useCorridas(allowed);
  const lanzar = useLanzarCorrida(list.reload);
  const anular = useAnularCorrida(list.reload);
  const [dialogo, setDialogo] = useState(false);
  const [creado, setCreado] = useState(null);
  const abrir = useCallback((id) => router.push(`/motored/pedidos/${id}`), [router]);
  const alCrear = useCallback((escenario) => { setDialogo(false); setCreado(escenario); list.reload(); }, [list]);
  if (!allowed) return null;
  // Scenarios are launched by ADMIN only (decision F4-8); the server answers 403 E-CORRIDA-062 to anyone else.
  const esAdmin = getRolActual() === 'ADMIN';
  const Frasco = ACTION_ICONS['Nuevo escenario'];
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap' }}>
        <h1 className="motored-h-pantalla">Pedidos</h1>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          {esAdmin && (
            <button
              type="button" className="motored-btn motored-btn-secondary"
              style={{ minHeight: '44px', display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}
              onClick={() => setDialogo(true)}
            >
              <Frasco size={16} aria-hidden="true" />
              Nuevo escenario
            </button>
          )}
          <button
            type="button" className="motored-btn motored-btn-secondary" style={{ minHeight: '44px' }}
            onClick={() => router.push('/motored/pedidos/topes')}
          >
            Topes por tienda
          </button>
        </div>
      </div>
      <AvisoAntiguedadBanner enabled={Boolean(allowed)} />
      {creado && <AvisoEscenario escenario={creado} onVer={abrir} />}
      <LanzarCorridaForm lanzar={lanzar} />
      <CorridasFiltros filters={list.filters} setFilter={list.setFilter} />
      <Cuerpo list={list} onOpen={abrir} onAnular={anular.abrir} />
      <AnularCorridaDialog anular={anular} />
      {esAdmin && dialogo && <EscenarioDialog onCerrar={() => setDialogo(false)} onCreada={alCrear} />}
    </div>
  );
}
