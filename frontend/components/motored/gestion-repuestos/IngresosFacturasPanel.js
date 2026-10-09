'use client';
/**
 * "Ingresos facturas" (Gestión repuestos): HMCL invoices still waiting for an
 * ingreso. KPIs, a per-store table and a per-invoice detail with filters and
 * history. `puedeConfirmar` (COORDINADOR_REPUESTOS only) adds the "Llegó" /
 * "No ha llegado" buttons; every other role reads. The page that mounts it
 * decides `puedeConfirmar` from the session role.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  confirmarIngreso, getIngresosDetalle, getIngresosPorTienda, getIngresosResumen,
} from '../../../lib/motored/gestionRepuestosApi';
import { fechaBogota } from '../../../lib/motored/fechas';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';
import IngresosKpis from './IngresosKpis';
import IngresosPorTienda, { ordenarTiendas } from './IngresosPorTienda';
import IngresosDetalle from './IngresosDetalle';
import { select, opcion, segmento } from './ingresosEstilos';

const ESTADOS_FILTRO = [
  [null, 'Todas'], ['LLEGO', 'Ya llegó sin ingresar'], ['SIN_CONFIRMAR', 'Sin confirmar'], ['NO_HA_LLEGADO', 'Aún no llega'],
];
// `min_dias` is inclusive on the API, so "> 7 días" asks for at least 8.
const EDADES = [[null, 'Todas'], [8, '> 7 días'], [16, '> 15 días']];
const MSG_DETALLE = 'No se pudo cargar el detalle de facturas.';

function Segmentos({ nombre, opciones, valor, onElegir }) {
  return (
    <div role="group" aria-label={nombre} style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '12px', fontWeight: 500 }}>
      {nombre}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
        {opciones.map(([v, texto]) => (
          <button key={texto} type="button" aria-pressed={valor === v} style={segmento(valor === v)} onClick={() => onElegir(v)}>{texto}</button>
        ))}
      </div>
    </div>
  );
}

export default function IngresosFacturasPanel({ puedeConfirmar = false }) {
  const [base, setBase] = useState(null); // { desde, resumen, tiendas }
  const [items, setItems] = useState([]);
  const [filtros, setFiltros] = useState({ sucursal: '', estado: null, min_dias: null });
  const [cargando, setCargando] = useState(true);
  const [ocupada, setOcupada] = useState(false);
  const [error, setError] = useState(null);
  const pedido = useRef(0);

  const cargarBase = useCallback(async () => {
    const [r, t] = await Promise.all([getIngresosResumen(), getIngresosPorTienda()]);
    setBase({ desde: r.verificable_desde, resumen: r.resumen, tiendas: t.tiendas || [] });
  }, []);

  useEffect(() => {
    let vigente = true;
    cargarBase().catch(() => { if (vigente) setError('No se pudo cargar el seguimiento de ingresos.'); });
    return () => { vigente = false; };
  }, [cargarBase]);

  useEffect(() => {
    const n = ++pedido.current;
    setCargando(true);
    getIngresosDetalle({
      sucursal: filtros.sucursal || undefined, estado: filtros.estado || undefined, min_dias: filtros.min_dias ?? undefined,
    })
      .then((r) => {
        if (n !== pedido.current) return;
        setItems(r.items || []);
        setCargando(false);
        setError((previo) => (previo === MSG_DETALLE ? null : previo));
      })
      .catch(() => {
        if (n === pedido.current) { setError(MSG_DETALLE); setCargando(false); }
      });
  }, [filtros]);

  const poner = (campo) => (valor) => setFiltros((f) => ({ ...f, [campo]: valor }));

  const confirmar = async (item, estado) => {
    setOcupada(true);
    setError(null);
    try {
      const nuevo = await confirmarIngreso({ factura: item.factura, sucursal_id: item.sucursal_id, estado });
      setItems((lista) => lista.map((i) => (
        i.factura === item.factura && i.sucursal_id === item.sucursal_id ? { ...i, ...nuevo } : i)));
      cargarBase().catch(() => {});
    } catch (e) {
      setError(mensajeConCodigo(e, 'No se pudo guardar la confirmación.'));
    } finally {
      setOcupada(false);
    }
  };

  const sinDatos = base && base.desde === null;
  const tiendas = base ? ordenarTiendas(base.tiendas) : [];

  return (
    <div style={{ maxWidth: '1240px', display: 'flex', flexDirection: 'column', gap: '22px' }}>
      <header style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <h1 style={{ margin: 0, fontSize: '30px', fontWeight: 700, letterSpacing: '-.02em' }}>Ingresos facturas</h1>
          <p style={{ margin: 0, fontSize: '14px' }}>
            Seguimiento de facturas de pedido pendientes por ingresar
            {base && base.desde ? ` · Verificable desde el ${fechaBogota(base.desde)}` : ''}
          </p>
        </div>
        {!sinDatos && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '14px 22px', alignItems: 'flex-end' }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '12px', fontWeight: 500 }}>
              Tienda
              <select style={select} value={filtros.sucursal} onChange={(e) => poner('sucursal')(e.target.value)}>
                <option style={opcion} value="">Todas las tiendas</option>
                {tiendas.map((t) => (
                  <option key={t.sucursal_id} style={opcion} value={t.sucursal_id}>{t.tienda}</option>
                ))}
              </select>
            </label>
            <Segmentos nombre="Estado" opciones={ESTADOS_FILTRO} valor={filtros.estado} onElegir={poner('estado')} />
            <Segmentos nombre="Antigüedad" opciones={EDADES} valor={filtros.min_dias} onElegir={poner('min_dias')} />
          </div>
        )}
      </header>

      {error && <p role="alert" style={{ margin: 0, fontSize: '13px', color: 'var(--motored-danger, #c0392b)' }}>{error}</p>}

      {sinDatos && (
        <p style={{ margin: 0, fontSize: '15px' }}>Carga ingresos de facturas para empezar el seguimiento</p>
      )}

      {base && !sinDatos && (
        <>
          <IngresosKpis resumen={base.resumen} />
          <IngresosPorTienda tiendas={base.tiendas} onElegir={poner('sucursal')} />
          <IngresosDetalle
            items={items} total={base.resumen.pendientes} cargando={cargando}
            puedeConfirmar={puedeConfirmar} ocupada={ocupada} onConfirmar={confirmar}
          />
          <p style={{ margin: 0, fontSize: '12.5px' }}>Las facturas salen del seguimiento cuando aparecen en Ingresos de facturas.</p>
        </>
      )}
    </div>
  );
}
