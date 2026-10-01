'use client';
/**
 * Lifecycle actions of the pedidos of a corrida (cerrar, reabrir, marcar como
 * enviado, corregir el número, exportar, recalcular fallidas): which dialog is
 * open, the request in flight, the coded error shown inside the dialog and the
 * notice that stays on the screen after an action. `alCambiar` runs after any
 * change so the screen reads the fresh states.
 */
import { useCallback, useState } from 'react';
import {
  cerrarLote, cerrarTienda, corregirEnvio, crearCorrida, enviarLote, enviarTienda,
  exportarTienda, exportarZip, reabrirTienda,
} from '../../../lib/motored/pedidosApi';
import { mensajeConCodigo } from '../../../lib/motored/httpErrors';
import { plural } from './formato';

const ACCION_A_DIALOGO = { cerrar: 'cerrar', reabrir: 'reabrir', enviar: 'enviar', corregir_envio: 'corregir' };

const ids = (tiendas) => tiendas.map((t) => t.sucursal_id);

/** Runs the request of the open dialog; resolves the notice to show afterwards (or `null`). */
async function ejecutar({ tipo, tiendas, todas, contexto }, corridaId, datos) {
  const [primera] = tiendas;
  switch (tipo) {
    case 'cerrar': {
      if (tiendas.length === 1 && !todas) { await cerrarTienda(corridaId, primera.sucursal_id); return null; }
      const res = await cerrarLote(corridaId, todas ? undefined : ids(tiendas));
      const n = res.cerradas.length;
      return { tipo: 'ok', texto: `Se ${plural(n, 'cerró', 'cerraron')} ${n} ${plural(n, 'pedido', 'pedidos')}.` };
    }
    case 'reabrir':
      await reabrirTienda(corridaId, primera.sucursal_id, datos);
      return null;
    case 'enviar': {
      if (tiendas.length === 1) {
        const { numero_pedido_proveedor: numero, fecha_envio: fecha } = datos[0];
        await enviarTienda(corridaId, primera.sucursal_id, { numero_pedido_proveedor: numero, fecha_envio: fecha });
        return null;
      }
      const res = await enviarLote(corridaId, datos);
      const n = res.enviadas.length;
      return { tipo: 'ok', texto: `Se ${plural(n, 'marcó', 'marcaron')} ${n} ${plural(n, 'pedido como enviado', 'pedidos como enviados')}.` };
    }
    case 'corregir':
      await corregirEnvio(corridaId, primera.sucursal_id, datos);
      return null;
    default: {
      const nueva = await crearCorrida({
        fecha_corte: contexto.fecha_corte, sucursal_ids: ids(tiendas), nota: `Recálculo de fallidas de ${contexto.codigo}`,
      });
      return { tipo: 'ok', texto: `Corrida ${nueva.codigo} creada: se está calculando.`, corridaId: nueva.id };
    }
  }
}

function avisoDeDescarga({ nombre, omitidas }) {
  const n = omitidas.length;
  const texto = `Se descargó ${nombre}.`;
  const cabecera = `${n} ${plural(n, 'tienda no se incluyó', 'tiendas no se incluyeron')} en el archivo:`;
  return { tipo: 'ok', texto, omitidas: n > 0 ? { cabecera, filas: omitidas.map((o) => `${o.nombre}: ${o.motivo}`) } : null };
}

export default function useAccionesPedido(corridaId, alCambiar) {
  const [dialogo, setDialogo] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState('');
  const [aviso, setAviso] = useState(null);

  const abrir = useCallback((tipo, tiendas, extra = {}) => {
    setError('');
    setDialogo({ tipo, tiendas, ...extra });
  }, []);
  const cancelar = useCallback(() => setDialogo(null), []);
  const descartarAviso = useCallback(() => setAviso(null), []);

  const confirmar = useCallback(async (datos) => {
    setOcupado(true);
    setError('');
    try {
      const resultado = await ejecutar(dialogo, corridaId, datos);
      setDialogo(null);
      setAviso(resultado);
      alCambiar?.();
    } catch (fallo) {
      setError(mensajeConCodigo(fallo, 'No se pudo completar la acción.'));
    } finally {
      setOcupado(false);
    }
  }, [dialogo, corridaId, alCambiar]);

  const descargar = useCallback(async (pedir) => {
    setOcupado(true);
    setAviso(null);
    try {
      setAviso(avisoDeDescarga(await pedir()));
    } catch (fallo) {
      setAviso({ tipo: 'error', texto: mensajeConCodigo(fallo, 'No se pudo exportar el pedido.') });
    } finally {
      setOcupado(false);
    }
  }, []);

  const alAccionar = useCallback((clave, tienda) => {
    if (clave === 'exportar') return descargar(() => exportarTienda(corridaId, tienda.sucursal_id));
    return abrir(ACCION_A_DIALOGO[clave], [tienda]);
  }, [abrir, descargar, corridaId]);

  const exportarTodas = useCallback(() => descargar(() => exportarZip(corridaId)), [descargar, corridaId]);

  return { dialogo, ocupado, error, aviso, abrir, cancelar, confirmar, alAccionar, exportarTodas, descartarAviso };
}
