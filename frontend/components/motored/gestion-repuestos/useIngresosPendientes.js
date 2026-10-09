'use client';
import { useCallback, useEffect, useState } from 'react';
import { confirmarIngreso, getIngresosDetalle } from '../../../lib/motored/gestionRepuestosApi';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';

const MSG_CARGA = 'No se pudo cargar el seguimiento de ingresos.';

/** Loads the whole pending list once (filters are applied in memory) and reloads it after a confirmation. */
export default function useIngresosPendientes() {
  const [desde, setDesde] = useState(undefined); // undefined = loading, null = no ingreso loaded
  const [items, setItems] = useState([]);
  const [ocupada, setOcupada] = useState(false);
  const [error, setError] = useState(null);

  const cargar = useCallback(async () => {
    const r = await getIngresosDetalle();
    setDesde(r.verificable_desde ?? null);
    setItems(r.items || []);
  }, []);

  useEffect(() => {
    let vigente = true;
    cargar().catch(() => { if (vigente) setError(MSG_CARGA); });
    return () => { vigente = false; };
  }, [cargar]);

  const confirmar = async (item, estado) => {
    setOcupada(true);
    setError(null);
    try {
      const nuevo = await confirmarIngreso({ factura: item.factura, sucursal_id: item.sucursal_id, estado });
      setItems((lista) => lista.map((i) => (
        i.factura === item.factura && i.sucursal_id === item.sucursal_id ? { ...i, ...nuevo } : i)));
      // The confirmation is already saved and shown; a failed reload only leaves the previous numbers.
      cargar().catch(() => {});
    } catch (e) {
      setError(mensajeConCodigo(e, 'No se pudo guardar la confirmación.'));
    } finally {
      setOcupada(false);
    }
  };

  return { desde, items, error, ocupada, confirmar };
}
