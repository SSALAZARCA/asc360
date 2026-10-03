/**
 * Carga de referencias como REEMPLAZO COMPLETO (motored-referencia-identidad,
 * R2): despues de validar se muestra un resumen en castellano y recien con
 * "Confirmar reemplazo" se aplica. Si se desactiva mas del 10% de las activas
 * hay una segunda confirmacion explicita. Las demas entidades siguen con
 * "Cargar".
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
    inactivar: {
      total: 3, con_ventas_6m: 1, con_inventario: 1,
      muestra: [
        { codigo: 'VEN-1', nombre: 'Filtro', con_ventas_6m: true, con_inventario: false },
        { codigo: 'STK-1', nombre: null, con_ventas_6m: false, con_inventario: true },
        { codigo: 'QUI-1', nombre: null, con_ventas_6m: false, con_inventario: false },
      ],
    },
    reactivar: grupo(1, [{ codigo: 'VUELVE-1' }]),
    vinculos_sustituta_limpiados: grupo(1, [{ codigo: 'VIEJA-1', sustituta: 'MUEVE-1' }]),
    activas_actuales: 100, pct_inactivar: 0.03, requiere_doble_confirmacion: false,
    ...extra,
  };
}

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
    expect(q.getByText(/Se desactivan 3 referencias que no están en el archivo/)).toBeInTheDocument();
    expect(q.getByText(/Se reactivan 1 referencias/)).toBeInTheDocument();
    expect(q.getByText(/Se quitan 1 vínculos de sustituta/)).toBeInTheDocument();
    expect(q.getByText(/VIEJA-1 \(sustituta: MUEVE-1\)/)).toBeInTheDocument();
  });

  it('resalta las desactivadas que vendieron en los ultimos 6 meses o tienen stock', async () => {
    await subirCsvYValidar(resumen());

    const q = within(screen.getByRole('region', { name: /Resumen del reemplazo/i }));
    expect(q.getByText(/Ojo: 1 vendieron en los últimos 6 meses y 1 tienen stock/)).toBeInTheDocument();
    expect(q.getByText(/\(vendió en los últimos 6 meses\)/)).toBeInTheDocument();
    expect(q.getByText(/\(tiene stock\)/)).toBeInTheDocument();
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

describe('confirmar el reemplazo', () => {
  it('el boton llama a aplicar con la bandera de confirmacion', async () => {
    await subirCsvYValidar(resumen());

    fireEvent.click(screen.getByText('Confirmar reemplazo'));

    await waitFor(() => expect(mockSubirCarga).toHaveBeenCalledTimes(1));
    const [entidad, filas, opciones] = mockSubirCarga.mock.calls[0];
    expect(entidad).toBe('referencia');
    expect(filas).toEqual([{ codigo: 'REF1', proveedor_codigo: 'HMCL' }]);
    expect(opciones).toEqual({ confirmarReemplazo: true, confirmarInactivacionMasiva: false });
  });

  it('con mas del 10% a desactivar pide una segunda confirmacion explicita', async () => {
    await subirCsvYValidar(resumen({ pct_inactivar: 0.62, activas_actuales: 5, requiere_doble_confirmacion: true }));

    const boton = screen.getByText('Confirmar reemplazo');
    expect(boton).toBeDisabled();
    expect(screen.getByText(/62%/)).toBeInTheDocument();
    expect(screen.getByText(/consolidar sustituidas/)).toBeInTheDocument();
    fireEvent.click(boton);
    expect(mockSubirCarga).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('checkbox'));
    expect(boton).not.toBeDisabled();
    fireEvent.click(boton);

    await waitFor(() => expect(mockSubirCarga).toHaveBeenCalledTimes(1));
    expect(mockSubirCarga.mock.calls[0][2]).toEqual({ confirmarReemplazo: true, confirmarInactivacionMasiva: true });
  });

  it('sin necesidad de doble confirmacion no muestra el checkbox', async () => {
    await subirCsvYValidar(resumen());

    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
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
    expect(mockSubirArchivo.mock.calls[0][2]).toEqual({ confirmarReemplazo: true, confirmarInactivacionMasiva: false });
  });
});

describe('despues de aplicar el reemplazo', () => {
  it('muestra el resultado aplicado y ya no deja confirmar de nuevo', async () => {
    mockSubirCarga.mockResolvedValue({
      ok: true, total_filas: 120, insertados: 2, actualizados: 1,
      resumen_reemplazo: resumen({ inactivar_por_sustituta: grupo(2, [{ codigo: 'S-1', nombre: null }]) }),
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

describe('doble confirmacion al cambiar el resumen', () => {
  it('re-validar con un resumen nuevo desmarca la confirmacion masiva', async () => {
    const masivo = () => resumen({ pct_inactivar: 0.62, activas_actuales: 5, requiere_doble_confirmacion: true });
    await subirCsvYValidar(masivo());
    fireEvent.click(screen.getByRole('checkbox'));
    expect(screen.getByRole('checkbox')).toBeChecked();
    expect(screen.getByText('Confirmar reemplazo')).not.toBeDisabled();

    mockValidarCarga.mockResolvedValue({ ok: true, total_filas: 120, resumen_reemplazo: masivo() });
    fireEvent.click(screen.getByText('Validar'));

    await waitFor(() => expect(mockValidarCarga).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByRole('checkbox')).not.toBeChecked());
    expect(screen.getByText('Confirmar reemplazo')).toBeDisabled();
  });
});

