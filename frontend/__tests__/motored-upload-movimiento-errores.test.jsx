/**
 * `UploadMovimientoModal` shows the server's message when `POST /cargas`
 * fails, never a bare "HTTP 400". The real `api.js`/`motoredFetch` path is
 * exercised: only `fetch` is mocked.
 *
 * - wrong tab: 400 with an object `detail` carrying `mensaje`;
 * - unreadable file: 400 with a string `detail`;
 * - too large: 413 with a string `detail`;
 * - an error with no usable detail still says something in Spanish.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import UploadMovimientoModal from '../components/motored/cargas/UploadMovimientoModal';

function respuesta(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
    clone() { return this; },
  };
}

function xlsxFile() {
  return new File(['dummy'], 'archivo.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

async function subirCon(status, body) {
  global.fetch = jest.fn().mockResolvedValue(respuesta(status, body));
  const { container } = render(
    <UploadMovimientoModal tipo="INGRESOS_FACTURAS" label="Ingresos de facturas" onClose={jest.fn()} />
  );
  const input = container.querySelector('input[type="file"]');
  fireEvent.change(input, { target: { files: [xlsxFile()] } });
  fireEvent.click(screen.getByRole('button', { name: /subir/i }));
  await waitFor(() => expect(global.fetch).toHaveBeenCalled());
}

const originalFetch = global.fetch;
afterEach(() => {
  global.fetch = originalFetch;
});

describe('UploadMovimientoModal — server error messages', () => {
  it('shows detail.mensaje for a wrong-tab 400', async () => {
    const mensaje = 'Este archivo no parece de Ingresos de facturas: le faltan las columnas '
      + 'Dct.referencia. ¿Lo quiso subir en otra pestaña?';
    await subirCon(400, {
      detail: {
        tipo_declarado: 'INGRESOS_FACTURAS',
        sin_coincidencia: false,
        columnas_faltantes: ['Dct.referencia'],
        mensaje,
      },
    });

    expect(await screen.findByText(mensaje)).toBeInTheDocument();
    expect(screen.queryByText(/HTTP 400/)).not.toBeInTheDocument();
  });

  it('shows a string detail for an unreadable-file 400', async () => {
    const mensaje = 'No se pudo leer el archivo. Verificá que sea un .xlsx válido.';
    await subirCon(400, { detail: mensaje });

    expect(await screen.findByText(mensaje)).toBeInTheDocument();
    expect(screen.queryByText(/HTTP 400/)).not.toBeInTheDocument();
  });

  it('shows the server message for a 413', async () => {
    const mensaje = 'El archivo supera el límite de 20MB';
    await subirCon(413, { detail: mensaje });

    expect(await screen.findByText(mensaje)).toBeInTheDocument();
  });

  it('never shows a bare HTTP status when the server sends no usable detail', async () => {
    await subirCon(400, { detail: { tipo_declarado: 'INGRESOS_FACTURAS' } });

    expect(await screen.findByText(/No se pudo subir el archivo/)).toBeInTheDocument();
    expect(screen.queryByText(/^HTTP 400$/)).not.toBeInTheDocument();
  });
});
