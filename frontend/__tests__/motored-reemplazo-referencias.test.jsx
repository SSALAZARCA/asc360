/**
 * Carga de referencias como REEMPLAZO COMPLETO (motored-referencia-identidad,
 * R2): despues de validar se muestra un resumen en castellano y recien con
 * "Confirmar reemplazo" se aplica. R3: las referencias ausentes del archivo se
 * listan con un checkbox "Inactivar" (todas SIN marcar) y solo se inactivan las
 * elegidas; si lo elegido (mas las que quedan inactivas por sustituta) pasa del
 * 10% de las activas hay una segunda confirmacion explicita. Las demas
 * entidades siguen con "Cargar".
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

const mockValidarCarga = jest.fn();
const mockSubirCarga = jest.fn();
const mockValidarArchivo = jest.fn();
const mockSubirArchivo = jest.fn();
jest.mock('../lib/motored/api', () => ({
  validarCarga: (...a) => mockValidarCarga(...a),
  subirCarga: (...a) => mockSubirCarga(...a),
  validarCargaArchivo: (...a) => mockValidarArchivo(...a),
  subirCargaArchivo: (...a) => mockSubirArchivo(...a),
}));

import BulkUploadModal from '../components/motored/maestros/BulkUploadModal';

const grupo = (total = 0, muestra = []) => ({ total, muestra });
function resumen(extra = {}) {
  return {
    total_archivo: 120,
    crear: grupo(2, [{ codigo: 'NUEVA-1', proveedor: 'HMCL' }, { codigo: 'NUEVA-2', proveedor: 'OTRO' }]),
    actualizar: grupo(1, [{ codigo: 'ACT-1', campos: ['nombre', 'precio_normal'] }]),
    mover_proveedor: grupo(1, [{ codigo: 'MUEVE-1', proveedor_anterior: 'HMCL', proveedor_nuevo: 'OTRO' }]),
    ausentes: {
      total: 3, con_ventas_6m: 1, con_inventario: 1,
      items: [
        { codigo: 'VEN-1', nombre: 'Filtro', proveedor: 'HMCL', con_ventas_6m: true, con_inventario: false },
        { codigo: 'STK-1', nombre: null, proveedor: 'HMCL', con_ventas_6m: false, con_inventario: true },
        { codigo: 'QUI-1', nombre: null, proveedor: 'OTRO', con_ventas_6m: false, con_inventario: false },
      ],
    },
    seleccionadas: 0,
    inactivar_por_sustituta: grupo(),
    reactivar: grupo(1, [{ codigo: 'VUELVE-1' }]),
    vinculos_sustituta_limpiados: grupo(1, [{ codigo: 'VIEJA-1', sustituta: 'MUEVE-1' }]),
    activas_actuales: 100, pct_inactivar: 0, pct_inactivar_si_todas: 0.03, requiere_doble_confirmacion: false,
    ...extra,
  };
}

// 20 activas y 5 ausentes: 2 elegidas = 10% (no exige), 3 elegidas = 15% (exige).
function resumenMasivo(extra = {}) {
  const items = ['A1', 'A2', 'A3', 'A4', 'A5'].map((codigo) => (
    { codigo, nombre: null, proveedor: 'HMCL', con_ventas_6m: false, con_inventario: false }));
  return resumen({
    ausentes: { total: 5, con_ventas_6m: 0, con_inventario: 0, items },
    activas_actuales: 20, pct_inactivar_si_todas: 0.25, ...extra,
  });
}

const marcar = (codigo) => fireEvent.click(screen.getByRole('checkbox', { name: new RegExp(`Inactivar ${codigo}\\b`) }));
const checkboxesDeFilas = () => screen.getAllByRole('checkbox').filter((c) => /^Inactivar /.test(c.getAttribute('aria-label') || ''));

async function subirCsvYValidar(resumenValidar) {
  mockValidarCarga.mockResolvedValue({ ok: true, total_filas: 120, resumen_reemplazo: resumenValidar });
  const { container } = render(<BulkUploadModal entidad="referencia" onClose={jest.fn()} onSuccess={jest.fn()} />);
  const csv = 'Código,Código del proveedor\nREF1,HMCL\n';
  fireEvent.change(container.querySelector('input[type="file"]'), {
    target: { files: [new File([csv], 'referencias.csv', { type: 'text/csv' })] },
  });
  await waitFor(() => expect(screen.getByText(/Vista previa/i)).toBeInTheDocument());
  fireEvent.click(screen.getByText('Validar'));
  await screen.findByText(/Esto es lo que va a pasar/i);
}

beforeEach(() => {
  [mockValidarCarga, mockSubirCarga, mockValidarArchivo, mockSubirArchivo].forEach((m) => m.mockReset());
  mockSubirCarga.mockResolvedValue({ ok: true, total_filas: 120, insertados: 2, actualizados: 1 });
});

describe('resumen del reemplazo de referencias', () => {
  it('cuenta en castellano lo que se crea, actualiza, mueve, desactiva y reactiva', async () => {
    await subirCsvYValidar(resumen());

    const panel = screen.getByRole('region', { name: /Resumen del reemplazo/i });
    const q = within(panel);
    expect(q.getByText(/Se crean 2 referencias nuevas/)).toBeInTheDocument();
    expect(q.getByText(/NUEVA-2 \(OTRO\)/)).toBeInTheDocument();
    expect(q.getByText(/Se actualizan 1 referencias/)).toBeInTheDocument();
    expect(q.getByText(/ACT-1: cambia nombre, precio_normal/)).toBeInTheDocument();
    expect(q.getByText(/Cambian de proveedor 1 referencias/)).toBeInTheDocument();
    expect(q.getByText(/MUEVE-1: HMCL → OTRO/)).toBeInTheDocument();
    expect(q.getByText(/No vienen en el archivo: por defecto siguen activas\. Marcá las que quieras inactivar\./)).toBeInTheDocument();
    expect(q.queryByText(/Se desactivan 3 referencias que no están en el archivo/)).not.toBeInTheDocument();
    expect(q.getByText(/Se reactivan 1 referencias/)).toBeInTheDocument();
    expect(q.getByText(/Se quitan 1 vínculos de sustituta/)).toBeInTheDocument();
    expect(q.getByText(/VIEJA-1 \(sustituta: MUEVE-1\)/)).toBeInTheDocument();
  });

  it('resalta las desactivadas que vendieron en los ultimos 6 meses o tienen stock', async () => {
    await subirCsvYValidar(resumen());

    const q = within(screen.getByRole('region', { name: /Resumen del reemplazo/i }));
    expect(q.getByText(/Ojo: 1 vendieron en los últimos 6 meses y 1 tienen stock/)).toBeInTheDocument();
    expect(q.getByText('Vendió en los últimos 6 meses')).toBeInTheDocument();
    expect(q.getByText('Tiene stock')).toBeInTheDocument();
  });

  it('no ofrece el boton Cargar para referencias: solo "Confirmar reemplazo"', async () => {
    await subirCsvYValidar(resumen());

    expect(screen.queryByText('Cargar')).not.toBeInTheDocument();
    expect(screen.getByText('Confirmar reemplazo')).toBeInTheDocument();
  });

  it('otras entidades conservan el boton Cargar y no muestran el resumen', async () => {
    render(<BulkUploadModal entidad="proveedor" onClose={jest.fn()} onSuccess={jest.fn()} />);

    expect(screen.getByText('Cargar')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: /Resumen del reemplazo/i })).not.toBeInTheDocument();
  });
});

describe('referencias ausentes: inactivar es opt-in', () => {
  it('lista cada ausente con su proveedor y un checkbox Inactivar SIN marcar', async () => {
    await subirCsvYValidar(resumen());

    const q = within(screen.getByRole('region', { name: /Resumen del reemplazo/i }));
    expect(checkboxesDeFilas()).toHaveLength(3);
    checkboxesDeFilas().forEach((c) => expect(c).not.toBeChecked());
    expect(q.getByText(/VEN-1/)).toBeInTheDocument();
    expect(q.getByText(/Filtro/)).toBeInTheDocument();
    expect(q.getAllByText(/HMCL/).length).toBeGreaterThan(0);
    expect(q.getByText(/Se inactivarán 0 de 3/)).toBeInTheDocument();
  });

  it('muestra la lista completa (mas de 50) dentro de un area con scroll', async () => {
    const items = Array.from({ length: 120 }, (_, i) => (
      { codigo: `X-${i}`, nombre: null, proveedor: 'HMCL', con_ventas_6m: false, con_inventario: false }));
    await subirCsvYValidar(resumen({ ausentes: { total: 120, con_ventas_6m: 0, con_inventario: 0, items } }));

    expect(checkboxesDeFilas()).toHaveLength(120);
    const lista = screen.getByRole('list', { name: /Referencias ausentes del archivo/i });
    expect(lista.style.overflowY).toBe('auto');
    expect(lista.style.maxHeight).not.toBe('');
  });

  it('marcar una fila actualiza el contador en vivo', async () => {
    await subirCsvYValidar(resumen());

    marcar('VEN-1');
    expect(screen.getByText(/Se inactivarán 1 de 3/)).toBeInTheDocument();
    marcar('STK-1');
    expect(screen.getByText(/Se inactivarán 2 de 3/)).toBeInTheDocument();
    marcar('VEN-1');
    expect(screen.getByText(/Se inactivarán 1 de 3/)).toBeInTheDocument();
  });

  it('"Marcar todas" marca todas y "Quitar selección" las desmarca', async () => {
    await subirCsvYValidar(resumen());

    fireEvent.click(screen.getByRole('button', { name: 'Marcar todas' }));
    checkboxesDeFilas().forEach((c) => expect(c).toBeChecked());
    expect(screen.getByText(/Se inactivarán 3 de 3/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Quitar selección' }));
    checkboxesDeFilas().forEach((c) => expect(c).not.toBeChecked());
    expect(screen.getByText(/Se inactivarán 0 de 3/)).toBeInTheDocument();
  });

  it('"Marcar solo las que no tienen ventas ni inventario" deja afuera las resaltadas', async () => {
    await subirCsvYValidar(resumen());
    marcar('VEN-1');

    fireEvent.click(screen.getByRole('button', { name: 'Marcar solo las que no tienen ventas ni inventario' }));

    expect(screen.getByRole('checkbox', { name: /Inactivar QUI-1\b/ })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /Inactivar VEN-1\b/ })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: /Inactivar STK-1\b/ })).not.toBeChecked();
    expect(screen.getByText(/Se inactivarán 1 de 3/)).toBeInTheDocument();
  });

  it('aplicar manda solo los codigos elegidos', async () => {
    await subirCsvYValidar(resumen());
    marcar('QUI-1');
    marcar('STK-1');

    fireEvent.click(screen.getByText('Confirmar reemplazo'));

    await waitFor(() => expect(mockSubirCarga).toHaveBeenCalledTimes(1));
    const opciones = mockSubirCarga.mock.calls[0][2];
    expect([...opciones.codigosInactivar].sort()).toEqual(['QUI-1', 'STK-1']);
    expect(opciones.confirmarReemplazo).toBe(true);
  });

  it('un resumen nuevo (re-validar) nace sin ninguna marcada', async () => {
    await subirCsvYValidar(resumen());
    marcar('VEN-1');
    expect(screen.getByText(/Se inactivarán 1 de 3/)).toBeInTheDocument();

    mockValidarCarga.mockResolvedValue({ ok: true, total_filas: 120, resumen_reemplazo: resumen() });
    fireEvent.click(screen.getByText('Validar'));

    await waitFor(() => expect(mockValidarCarga).toHaveBeenCalledTimes(2));
    await screen.findByText(/Se inactivarán 0 de 3/);
    checkboxesDeFilas().forEach((c) => expect(c).not.toBeChecked());
  });
});

describe('confirmar el reemplazo', () => {
  it('el boton llama a aplicar con la bandera de confirmacion', async () => {
    await subirCsvYValidar(resumen());

    fireEvent.click(screen.getByText('Confirmar reemplazo'));

    await waitFor(() => expect(mockSubirCarga).toHaveBeenCalledTimes(1));
    const [entidad, filas, opciones] = mockSubirCarga.mock.calls[0];
    expect(entidad).toBe('referencia');
    expect(filas).toEqual([{ codigo: 'REF1', proveedor_codigo: 'HMCL' }]);
    expect(opciones).toEqual({ confirmarReemplazo: true, confirmarInactivacionMasiva: false, codigosInactivar: [] });
  });

  it('la segunda confirmacion aparece solo cuando lo elegido pasa del 10%', async () => {
    await subirCsvYValidar(resumenMasivo());
    const boton = screen.getByText('Confirmar reemplazo');
    expect(screen.queryByRole('checkbox', { name: /Entiendo/ })).not.toBeInTheDocument();

    marcar('A1');
    marcar('A2'); // 2 de 20 = 10%: no exige
    expect(screen.queryByRole('checkbox', { name: /Entiendo/ })).not.toBeInTheDocument();
    expect(boton).not.toBeDisabled();

    marcar('A3'); // 3 de 20 = 15%: exige
    const entiendo = screen.getByRole('checkbox', { name: /Entiendo/ });
    expect(screen.getByText(/15%/)).toBeInTheDocument();
    expect(boton).toBeDisabled();
    fireEvent.click(boton);
    expect(mockSubirCarga).not.toHaveBeenCalled();

    fireEvent.click(entiendo);
    expect(boton).not.toBeDisabled();
    fireEvent.click(boton);

    await waitFor(() => expect(mockSubirCarga).toHaveBeenCalledTimes(1));
    const opciones = mockSubirCarga.mock.calls[0][2];
    expect(opciones.confirmarInactivacionMasiva).toBe(true);
    expect(opciones.codigosInactivar).toHaveLength(3);
  });

  it('las que quedan inactivas por sustituta cuentan para el 10% de la seleccion', async () => {
    // 20 activas, 1 por sustituta (5%): con 2 elegidas son 3 = 15%.
    await subirCsvYValidar(resumenMasivo({ inactivar_por_sustituta: grupo(1, [{ codigo: 'S-1', nombre: null }]) }));

    marcar('A1');
    expect(screen.queryByRole('checkbox', { name: /Entiendo/ })).not.toBeInTheDocument();
    marcar('A2');
    expect(screen.getByRole('checkbox', { name: /Entiendo/ })).toBeInTheDocument();
  });

  it('sin elegir nada no pide doble confirmacion aunque falten muchas', async () => {
    await subirCsvYValidar(resumenMasivo());

    fireEvent.click(screen.getByText('Confirmar reemplazo'));

    await waitFor(() => expect(mockSubirCarga).toHaveBeenCalledTimes(1));
    expect(mockSubirCarga.mock.calls[0][2]).toEqual({
      confirmarReemplazo: true, confirmarInactivacionMasiva: false, codigosInactivar: [],
    });
  });

  it('sin necesidad de doble confirmacion no muestra el checkbox de confirmacion', async () => {
    await subirCsvYValidar(resumen());

    expect(screen.queryByRole('checkbox', { name: /Entiendo/ })).not.toBeInTheDocument();
  });

  it('si aplicar falla (409) mantiene el resumen y muestra el motivo', async () => {
    mockSubirCarga.mockRejectedValue(new Error('Confirme la desactivación masiva'));
    await subirCsvYValidar(resumen());

    fireEvent.click(screen.getByText('Confirmar reemplazo'));

    expect(await screen.findByText(/Confirme la desactivación masiva/)).toBeInTheDocument();
    expect(screen.getByText('Confirmar reemplazo')).toBeInTheDocument();
  });

  it('con un .xlsx valida solo y aplica el archivo con la confirmacion', async () => {
    mockValidarArchivo.mockResolvedValue({ ok: true, total_filas: 3, resumen_reemplazo: resumen() });
    mockSubirArchivo.mockResolvedValue({ ok: true, total_filas: 3, insertados: 0, actualizados: 0 });
    const { container } = render(<BulkUploadModal entidad="referencia" onClose={jest.fn()} onSuccess={jest.fn()} />);
    const archivo = new File(['x'], 'referencias.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });

    fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [archivo] } });
    fireEvent.click(await screen.findByText('Confirmar reemplazo'));

    await waitFor(() => expect(mockSubirArchivo).toHaveBeenCalledTimes(1));
    expect(mockSubirArchivo.mock.calls[0][1]).toBe(archivo);
    expect(mockSubirArchivo.mock.calls[0][2]).toEqual({
      confirmarReemplazo: true, confirmarInactivacionMasiva: false, codigosInactivar: [],
    });
  });
});

describe('despues de aplicar el reemplazo', () => {
  it('muestra el resultado aplicado y ya no deja confirmar de nuevo', async () => {
    mockSubirCarga.mockResolvedValue({
      ok: true, total_filas: 120, insertados: 2, actualizados: 1,
      resumen_reemplazo: resumen({ seleccionadas: 3, inactivar_por_sustituta: grupo(2, [{ codigo: 'S-1', nombre: null }]) }),
    });
    await subirCsvYValidar(resumen());

    fireEvent.click(screen.getByText('Confirmar reemplazo'));

    expect(await screen.findByText(
      /Reemplazo aplicado: 2 creadas, 1 actualizadas, 1 movidas de proveedor, 5 inactivadas, 1 reactivadas/,
    )).toBeInTheDocument();
    expect(screen.queryByText('Confirmar reemplazo')).not.toBeInTheDocument();
    expect(screen.queryByText(/Todavía no se aplicó nada/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Revise el resumen/)).not.toBeInTheDocument();
    expect(mockSubirCarga).toHaveBeenCalledTimes(1);
  });

  it('volver a validar otro archivo despues de aplicar vuelve a mostrar el resumen', async () => {
    mockSubirCarga.mockResolvedValue({ ok: true, total_filas: 120, resumen_reemplazo: resumen() });
    await subirCsvYValidar(resumen());
    fireEvent.click(screen.getByText('Confirmar reemplazo'));
    await screen.findByText(/Reemplazo aplicado/);

    fireEvent.click(screen.getByText('Validar'));

    expect(await screen.findByText('Confirmar reemplazo')).toBeInTheDocument();
    expect(screen.queryByText(/Reemplazo aplicado/)).not.toBeInTheDocument();
  });
});

describe('doble confirmacion al cambiar la seleccion o el resumen', () => {
  async function conConfirmacionMarcada() {
    await subirCsvYValidar(resumenMasivo());
    ['A1', 'A2', 'A3'].forEach(marcar);
    fireEvent.click(screen.getByRole('checkbox', { name: /Entiendo/ }));
    expect(screen.getByRole('checkbox', { name: /Entiendo/ })).toBeChecked();
    expect(screen.getByText('Confirmar reemplazo')).not.toBeDisabled();
  }

  it('cambiar la seleccion desmarca la confirmacion masiva', async () => {
    await conConfirmacionMarcada();

    marcar('A4');

    expect(screen.getByRole('checkbox', { name: /Entiendo/ })).not.toBeChecked();
    expect(screen.getByText('Confirmar reemplazo')).toBeDisabled();
  });

  it('re-validar con un resumen nuevo vuelve a la seleccion vacia y sin confirmar', async () => {
    await conConfirmacionMarcada();

    mockValidarCarga.mockResolvedValue({ ok: true, total_filas: 120, resumen_reemplazo: resumenMasivo() });
    fireEvent.click(screen.getByText('Validar'));

    await waitFor(() => expect(mockValidarCarga).toHaveBeenCalledTimes(2));
    await screen.findByText(/Se inactivarán 0 de 5/);
    expect(screen.queryByRole('checkbox', { name: /Entiendo/ })).not.toBeInTheDocument();
    expect(screen.getByText('Confirmar reemplazo')).not.toBeDisabled();
  });
});
