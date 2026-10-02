'use client';
/** Topes por tienda: the cap mode switch and one cap per tienda. ADMIN edits; COMPRAS reads (the server enforces it). */
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import usePedidosGate from '../../../lib/motored/usePedidosGate';
import { getRolActual } from '../../../lib/motored/motoredFetch';
import ModoTope from './ModoTope';
import TopesTable from './TopesTable';
import useEdicionTopes from './useEdicionTopes';
import useTopes from './useTopes';
import { plural } from './formato';
import { cardStyle, errorStyle, mutedStyle, volverStyle } from './styles';
import { filtrarTiendas } from './tope';

function BarraGuardar({ edicion }) {
  const { cambios, errores, guardando, aviso, error, descartar, guardar } = edicion;
  const n = cambios.length;
  const invalido = Object.keys(errores).length > 0;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <button
          type="button" className="motored-btn motored-btn-primary" style={{ minHeight: '44px' }}
          disabled={guardando || n === 0 || invalido} onClick={guardar}
        >
          Guardar topes
        </button>
        <button
          type="button" className="motored-btn motored-btn-secondary" style={{ minHeight: '44px' }}
          disabled={guardando || (n === 0 && !invalido)} onClick={descartar}
        >
          Descartar cambios
        </button>
        {n > 0 && <span style={mutedStyle}>{`${n} ${plural(n, 'cambio', 'cambios')} sin guardar`}</span>}
      </div>
      {aviso && <p role="status" style={{ margin: 0, fontSize: '0.85rem', fontWeight: 600 }}>{aviso}</p>}
      {error && <p role="alert" style={errorStyle}>{error}</p>}
    </div>
  );
}

function Tabla({ data, editable, edicion }) {
  const [busqueda, setBusqueda] = useState('');
  const visibles = filtrarTiendas(data.topes, busqueda);
  return (
    <section style={cardStyle}>
      <input
        type="search" aria-label="Buscar tienda" placeholder="Buscar tienda" value={busqueda}
        onChange={(e) => setBusqueda(e.target.value)} style={{ height: '44px', maxWidth: '22rem', boxSizing: 'border-box' }}
      />
      {visibles.length === 0 ? (
        <p style={mutedStyle}>Sin tiendas para mostrar</p>
      ) : (
        <TopesTable topes={visibles} editable={editable} textos={edicion.textos} errores={edicion.errores} onCambiar={edicion.cambiar} />
      )}
      {editable && <BarraGuardar edicion={edicion} />}
    </section>
  );
}

function Pantalla({ data, editable, edicion }) {
  return (
    <>
      <ModoTope
        activo={data.modo_activo} desde={data.modo_vigente_desde} editable={editable}
        ocupado={edicion.cambiandoModo} error={edicion.errorModo} onCambiar={edicion.cambiarModo}
      />
      <Tabla data={data} editable={editable} edicion={edicion} />
    </>
  );
}

export default function TopesContainer() {
  const router = useRouter();
  const allowed = usePedidosGate();
  const { data, error, recargar } = useTopes(allowed);
  const edicion = useEdicionTopes(data ? data.topes : [], recargar);
  if (!allowed) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '100%' }}>
      <button type="button" className="motored-row-action" style={volverStyle} onClick={() => router.push('/motored/pedidos')}>
        ← Volver a pedidos
      </button>
      <h1 className="motored-h-pantalla">Topes por tienda</h1>
      {error && <p role="alert" style={errorStyle}>{error}</p>}
      {!error && !data && <p style={mutedStyle}>Cargando...</p>}
      {data && <Pantalla data={data} editable={getRolActual() === 'ADMIN'} edicion={edicion} />}
    </div>
  );
}
