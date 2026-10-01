'use client';
/**
 * frontend/components/motored/maestros/useVendedores.js
 *
 * Estado y acciones de la pestaña Vendedores: lista filtrada, sucursales y
 * usuarios para los selectores, la lista de "sin registrar" y las acciones
 * crear/editar/desactivar/reactivar. Cada acción recarga la lista y la de "sin
 * registrar" (una persona recién registrada deja de estar pendiente).
 */
import { useEffect, useState } from 'react';
import {
  listVendedores, createVendedor, updateVendedor, deactivateVendedor, reactivateVendedor,
  listVendedoresSinRegistrar, listUsuariosDisponibles, listMaestros,
} from '../../../lib/motored/api';

const FILTROS_VACIOS = { q: '', cargo: '', activo: '' };

async function intentar(setError, fallback, accion) {
  setError('');
  try {
    await accion();
    return true;
  } catch (err) {
    setError(err.message || fallback);
    return false;
  }
}

export default function useVendedores() {
  const [vendedores, setVendedores] = useState([]);
  const [filtros, setFiltros] = useState(FILTROS_VACIOS);
  const [sucursales, setSucursales] = useState([]);
  const [usuarios, setUsuarios] = useState([]);
  const [sinRegistrar, setSinRegistrar] = useState([]);
  const [sinRegistrarError, setSinRegistrarError] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const cargarLista = async (f = filtros) => {
    setLoading(true);
    const ok = await intentar(setError, 'Error al cargar vendedores', async () => {
      setVendedores(await listVendedores(f));
    });
    if (!ok) setVendedores([]);
    setLoading(false);
  };

  const cargarSinRegistrar = async () => {
    setSinRegistrarError('');
    try {
      setSinRegistrar(await listVendedoresSinRegistrar());
    } catch (err) {
      setSinRegistrarError(err.message || 'Error al cargar los vendedores sin registrar');
    }
  };

  const recargar = async () => { await Promise.all([cargarLista(), cargarSinRegistrar()]); };

  useEffect(() => {
    cargarLista(FILTROS_VACIOS);
    cargarSinRegistrar();
    listMaestros('sucursales').then(setSucursales).catch(() => setSucursales([]));
    listUsuariosDisponibles().then(setUsuarios).catch(() => setUsuarios([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const guardar = async (payload, editingId) => {
    const ok = await intentar(setError, 'Error al guardar el vendedor', () => (
      editingId ? updateVendedor(editingId, payload) : createVendedor(payload)
    ));
    if (ok) await recargar();
    return ok;
  };

  const desactivar = async (id) => {
    if (await intentar(setError, 'Error al desactivar el vendedor', () => deactivateVendedor(id))) await recargar();
  };

  const reactivar = async (id) => {
    if (await intentar(setError, 'Error al reactivar el vendedor', () => reactivateVendedor(id))) await recargar();
  };

  return {
    vendedores, filtros, setFiltros, sucursales, usuarios, sinRegistrar, sinRegistrarError,
    loading, error, aplicarFiltros: () => cargarLista(filtros), recargar, guardar, desactivar, reactivar,
  };
}
