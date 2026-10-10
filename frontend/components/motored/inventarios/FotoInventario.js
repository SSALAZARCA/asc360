'use client';
/**
 * "2. Foto del inventario" (WU11). Before the start: the store's latest
 * inventory and its age, and "Iniciar conteo". The start may warn twice
 * (`useIniciarConteo`): a stale inventory (409 INVENTARIO_ANTIGUO) and the
 * store's pending invoices / transfers (409 PENDIENTES_POR_SANEAR, WU15); a
 * dialog lets the leader start anyway. After the start: the frozen snapshot
 * the count runs against.
 */
import { useEffect, useState } from 'react';
import DialogoPedido from '../pedidos/DialogoPedido';
import InfoTooltip from '../InfoTooltip';
import { listarSucursalesConteo } from '../../../lib/motored/conteosApi';
import { fechaHoraBogota } from '../../../lib/motored/fechas';
import { formatEntero, formatPesos } from './conteosFormato';
import InventarioTienda from './InventarioTienda';
import useIniciarConteo from './useIniciarConteo';
import { avisoStyle, cardStyle, errorStyle, h2Style, mutedStyle } from './estilos';

const AYUDA_FOTO = 'Copia del inventario del sistema que se toma al iniciar. Contra ella se comparan las lecturas; las cargas posteriores en Maestros no la cambian.';

function useSucursal(conteo) {
  const [sucursal, setSucursal] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (conteo.estado !== 'PROGRAMADO') return undefined;
    let vivo = true;
    listarSucursalesConteo()
      .then((lista) => { if (vivo) setSucursal(lista.find((s) => s.id === conteo.sucursal.id) ?? { inventario: null }); })
      .catch((err) => { if (vivo) setError(err.message || 'No se pudo consultar el inventario de la tienda.'); });
    return () => { vivo = false; };
  }, [conteo.estado, conteo.sucursal.id]);
  return { sucursal, error };
}

function Snapshot({ snapshot }) {
  return (
    <div style={avisoStyle('success')}>
      <div>
        <strong>Foto tomada {fechaHoraBogota(snapshot.tomado_en)}</strong>
        <div>
          {formatEntero(snapshot.lineas)} referencias · {formatPesos(snapshot.valor_sistema)} al costo promedio
          {snapshot.sin_costo ? ` · ${formatEntero(snapshot.sin_costo)} sin costo` : ''}
        </div>
        <div>Archivo {snapshot.nombre_archivo || '—'} · cargado {fechaHoraBogota(snapshot.aplicado_en)}</div>
      </div>
    </div>
  );
}

export default function FotoInventario({ conteo, permisos, onIniciado }) {
  const { sucursal, error: errorSucursal } = useSucursal(conteo);
  const inicio = useIniciarConteo(conteo.id, onIniciado);
  const programado = conteo.estado === 'PROGRAMADO';

  return (
    <div style={cardStyle}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
        <h2 style={h2Style}>2. Foto del inventario</h2>
        <InfoTooltip text={AYUDA_FOTO} />
      </div>
      {programado && sucursal && <InventarioTienda sucursal={sucursal} />}
      {!programado && conteo.snapshot && <Snapshot snapshot={conteo.snapshot} />}
      {errorSucursal && <p role="alert" style={errorStyle}>{errorSucursal}</p>}
      <div style={mutedStyle}>
        Al iniciar, la aplicación guarda una copia de este inventario solo para esta tienda.
        Las cargas que haga después en Maestros no la cambian.
      </div>
      {programado && permisos.opera && (
        <button
          type="button" className="motored-btn motored-btn-primary" style={{ minHeight: '48px', fontSize: '1rem' }}
          disabled={inicio.ocupado} onClick={inicio.empezar}
        >
          Iniciar conteo de {conteo.sucursal.nombre}
        </button>
      )}
      {inicio.error && <p role="alert" style={errorStyle}>{inicio.error}</p>}
      {inicio.aviso && (
        <DialogoPedido
          titulo={inicio.aviso.titulo}
          descripcion={<span>{inicio.aviso.mensaje}</span>}
          ocupado={inicio.ocupado} textoConfirmar="Iniciar de todos modos"
          onConfirm={inicio.confirmar} onCancel={inicio.cancelar}
        />
      )}
    </div>
  );
}
