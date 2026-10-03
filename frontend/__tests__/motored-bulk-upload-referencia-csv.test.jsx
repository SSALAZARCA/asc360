/**
 * Referencia 9-column layout (owner request 2026-09-28) -- CSV path of
 * `BulkUploadModal.js`. The CSV is parsed in the browser, so header matching
 * must accept the new human headers, the old snake_case headers, and be
 * tolerant of case/accents/surrounding whitespace, exactly like the backend
 * Excel parser (`carga_excel.py`).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockValidarCarga = jest.fn();
const mockSubirCarga = jest.fn();
jest.mock('../lib/motored/api', () => ({
  validarCarga: (...args) => mockValidarCarga(...args),
  subirCarga: (...args) => mockSubirCarga(...args),
}));

import BulkUploadModal from '../components/motored/maestros/BulkUploadModal';

const grupo = () => ({ total: 0, muestra: [] });
const RESUMEN_VACIO = {
  total_archivo: 1, crear: grupo(), actualizar: grupo(), mover_proveedor: grupo(),
  inactivar: { ...grupo(), con_ventas_6m: 0, con_inventario: 0 }, reactivar: grupo(),
  vinculos_sustituta_limpiados: grupo(), activas_actuales: 10, pct_inactivar: 0,
  requiere_doble_confirmacion: false,
};

async function uploadCsvAndSubmit(content, entidad = 'referencia') {
  const { container } = render(
    <BulkUploadModal entidad={entidad} onClose={jest.fn()} onSuccess={jest.fn()} />
  );
  const input = container.querySelector('input[type="file"]');
  fireEvent.change(input, { target: { files: [new File([content], 'referencias.csv', { type: 'text/csv' })] } });
  await waitFor(() => expect(screen.getByText(/Vista previa/i)).toBeInTheDocument());
  if (entidad === 'referencia') {
    // Reemplazo completo: Validar -> resumen -> "Confirmar reemplazo".
    fireEvent.click(screen.getByText('Validar'));
    fireEvent.click(await screen.findByText('Confirmar reemplazo'));
  } else {
    fireEvent.click(screen.getByText('Cargar'));
  }
  await waitFor(() => expect(mockSubirCarga).toHaveBeenCalled());
  return mockSubirCarga.mock.calls[0][1];
}

beforeEach(() => {
  mockValidarCarga.mockReset().mockResolvedValue({
    ok: true, total_filas: 1, resumen_reemplazo: RESUMEN_VACIO,
  });
  mockSubirCarga.mockReset().mockResolvedValue({ ok: true, total_filas: 1, insertados: 1, actualizados: 0, advertencias: [] });
});

describe('BulkUploadModal — referencia CSV headers', () => {
  it('maps the new human headers to canonical keys', async () => {
    const filas = await uploadCsvAndSubmit(
      'Código;Código del proveedor;Nombre;Línea comercial;Unidad de empaque;Precio Normal antes de IVA;'
      + 'Precio Público antes de IVA;Código de referencia sustituta;Homologados otras marcas\n'
      + 'REF1;HMCL;Filtro;REPUESTOS;2;1000;1500;REF0;"YAM-1, HON-2"\n'
    );

    expect(filas).toEqual([{
      codigo: 'REF1',
      proveedor_codigo: 'HMCL',
      nombre: 'Filtro',
      linea_comercial: 'REPUESTOS',
      unidad_empaque: '2',
      precio_normal: '1000',
      precio_publico: '1500',
      sustituida_por_codigo: 'REF0',
      homologados: 'YAM-1, HON-2',
    }]);
  });

  it('still accepts the old snake_case headers and ignores precio_venta', async () => {
    const filas = await uploadCsvAndSubmit(
      'codigo,proveedor_codigo,precio_normal,precio_venta,precio_publico,sustituida_por_codigo\n'
      + 'REF1,HMCL,10,15,20,REF0\n'
    );

    expect(filas).toEqual([{
      codigo: 'REF1', proveedor_codigo: 'HMCL', precio_normal: '10', precio_publico: '20', sustituida_por_codigo: 'REF0',
    }]);
  });

  it('tolerates case, accents and surrounding whitespace in headers', async () => {
    const filas = await uploadCsvAndSubmit('  CODIGO ,código DEL proveedor , LINEA COMERCIAL\nREF1,HMCL,REPUESTOS\n');

    expect(filas).toEqual([{ codigo: 'REF1', proveedor_codigo: 'HMCL', linea_comercial: 'REPUESTOS' }]);
  });
});

describe('BulkUploadModal — CSV blank cells and duplicate headers', () => {
  it('keeps a blank boolean cell blank instead of turning it into false', async () => {
    const filas = await uploadCsvAndSubmit('Código,Nombre,Principal (Sí/No)\nHMCL,HMCL Colombia,\n', 'proveedor');

    expect(filas).toEqual([{ codigo: 'HMCL', nombre: 'HMCL Colombia', es_principal: '' }]);
  });

  it('rejects two headers that map to the same field with a clear error', async () => {
    const { container } = render(
      <BulkUploadModal entidad="referencia" onClose={jest.fn()} onSuccess={jest.fn()} />
    );
    const input = container.querySelector('input[type="file"]');
    const csv = 'Código,codigo,Código del proveedor\nREF1,REF2,HMCL\n';
    fireEvent.change(input, { target: { files: [new File([csv], 'referencias.csv', { type: 'text/csv' })] } });

    expect(await screen.findByText(/aparece más de una vez/i)).toBeInTheDocument();
    expect(screen.queryByText(/Vista previa/i)).not.toBeInTheDocument();
    expect(mockSubirCarga).not.toHaveBeenCalled();
  });
});
