/**
 * Client Ciudad/Departamento on `frontend/app/distribuidor/entrega/page.js`
 * must be DIVIPOLA-backed cascading selects (`GET /tenants/divipola/
 * departments`, `GET /tenants/divipola/cities?departamento=...`), same
 * catalog/UX as `frontend/app/tenants/page.js` -- never free text. Covers
 * the "Cliente" wizard step only; the edit-modal path is covered in
 * `distribuidor-entrega-page.test.jsx`'s existing edit-dialog tests.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockAuthFetch = jest.fn();
jest.mock('../lib/authFetch', () => ({
  authFetch: (...args) => mockAuthFetch(...args),
}));
jest.mock('../lib/api', () => ({
  getApiUrl: () => 'https://api.test',
}));
jest.mock('../lib/toast', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock('../app/admin-layout', () => {
  const MockAdminLayout = ({ children }) => <div>{children}</div>;
  MockAdminLayout.displayName = 'MockAdminLayout';
  return MockAdminLayout;
});

import DistribuidorEntregaPage from '../app/distribuidor/entrega/page';

function makeResponse(status, body) {
  return { ok: status >= 200 && status < 300, status, json: jest.fn().mockResolvedValue(body) };
}

const mockFetch = jest.fn();
global.fetch = (...args) => mockFetch(...args);

beforeEach(() => {
  mockAuthFetch.mockReset();
  mockAuthFetch.mockImplementation((url) => {
    if (typeof url === 'string' && url.includes('/vehicle-models')) return Promise.resolve(makeResponse(200, []));
    if (typeof url === 'string' && url === '/distributor/deliveries') return Promise.resolve(makeResponse(200, []));
    return Promise.resolve(makeResponse(200, {}));
  });
  mockFetch.mockReset();
  mockFetch.mockImplementation((url) => {
    if (typeof url === 'string' && url.includes('/tenants/divipola/departments')) {
      return Promise.resolve(makeResponse(200, ['Cundinamarca', 'Antioquia']));
    }
    if (typeof url === 'string' && url.includes('/tenants/divipola/cities')) {
      const dpto = decodeURIComponent(url.split('departamento=')[1] || '');
      const byDpto = { Cundinamarca: ['Bogotá'], Antioquia: ['Medellín'] };
      return Promise.resolve(makeResponse(200, byDpto[dpto] || []));
    }
    return Promise.resolve(makeResponse(200, []));
  });
  sessionStorage.setItem('um_user', JSON.stringify({ name: 'Test User', role: 'parts_dealer' }));
});

describe('DistribuidorEntregaPage — Cliente step Ciudad/Departamento are DIVIPOLA selects', () => {
  it('renders Departamento and Ciudad as <select>s, not free-text inputs', async () => {
    render(<DistribuidorEntregaPage />);

    const departamento = await screen.findByLabelText('Departamento');
    const ciudad = screen.getByLabelText('Ciudad');
    expect(departamento.tagName).toBe('SELECT');
    expect(ciudad.tagName).toBe('SELECT');
  });

  it('populates Departamento options from GET /tenants/divipola/departments', async () => {
    render(<DistribuidorEntregaPage />);

    const departamento = await screen.findByLabelText('Departamento');
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/tenants/divipola/departments'));
    });
    await waitFor(() => {
      expect(Array.from(departamento.options).map((o) => o.value)).toEqual(expect.arrayContaining(['Cundinamarca', 'Antioquia']));
    });
  });

  it('Ciudad starts disabled and enables once a Departamento is picked, populated with that department\'s cities', async () => {
    render(<DistribuidorEntregaPage />);

    const departamento = await screen.findByLabelText('Departamento');
    const ciudad = screen.getByLabelText('Ciudad');
    expect(ciudad).toBeDisabled();

    await waitFor(() => {
      expect(Array.from(departamento.options).map((o) => o.value)).toContain('Cundinamarca');
    });
    fireEvent.change(departamento, { target: { value: 'Cundinamarca' } });

    await waitFor(() => {
      expect(ciudad).not.toBeDisabled();
    });
    await waitFor(() => {
      expect(Array.from(ciudad.options).map((o) => o.value)).toContain('Bogotá');
    });
  });

  it('changing Departamento clears an already-selected Ciudad', async () => {
    render(<DistribuidorEntregaPage />);

    const departamento = await screen.findByLabelText('Departamento');
    const ciudad = screen.getByLabelText('Ciudad');
    await waitFor(() => expect(Array.from(departamento.options).map((o) => o.value)).toContain('Cundinamarca'));

    fireEvent.change(departamento, { target: { value: 'Cundinamarca' } });
    await waitFor(() => expect(Array.from(ciudad.options).map((o) => o.value)).toContain('Bogotá'));
    fireEvent.change(ciudad, { target: { value: 'Bogotá' } });
    expect(ciudad.value).toBe('Bogotá');

    fireEvent.change(departamento, { target: { value: 'Antioquia' } });

    expect(ciudad.value).toBe('');
  });

  it('the selected department/city are sent in the create payload', async () => {
    mockAuthFetch.mockImplementation((url, opts) => {
      if (typeof url === 'string' && url.includes('/vehicle-models')) return Promise.resolve(makeResponse(200, []));
      if (typeof url === 'string' && url === '/distributor/deliveries' && (!opts || !opts.method || opts.method === 'GET')) {
        return Promise.resolve(makeResponse(200, []));
      }
      if (typeof url === 'string' && url.startsWith('/vehicles/vin/')) {
        return Promise.resolve(makeResponse(200, { model: 'Renegade 200', year: 2023, color: 'Rojo', engine_number: 'ENG-999' }));
      }
      if (opts && opts.method === 'POST') {
        return Promise.resolve(makeResponse(201, {
          id: 'v-1', plate: 'ABC123', vin: null, model: null, color: null, year: null,
          engine_number: null, delivery_date: '2025-01-10', delivery_act_url: null, client_id: 'c-1',
        }));
      }
      return Promise.resolve(makeResponse(200, {}));
    });

    render(<DistribuidorEntregaPage />);

    fireEvent.change(screen.getByLabelText('Nombre del cliente'), { target: { value: 'Juan Perez' } });
    fireEvent.change(screen.getByLabelText('Cédula'), { target: { value: '123456789' } });
    const departamento = await screen.findByLabelText('Departamento');
    await waitFor(() => expect(Array.from(departamento.options).map((o) => o.value)).toContain('Cundinamarca'));
    fireEvent.change(departamento, { target: { value: 'Cundinamarca' } });
    const ciudad = screen.getByLabelText('Ciudad');
    await waitFor(() => expect(Array.from(ciudad.options).map((o) => o.value)).toContain('Bogotá'));
    fireEvent.change(ciudad, { target: { value: 'Bogotá' } });

    fireEvent.click(screen.getByRole('button', { name: /siguiente/i }));
    fireEvent.change(await screen.findByLabelText('Placa'), { target: { value: 'ABC123' } });
    fireEvent.change(screen.getByLabelText('VIN'), { target: { value: '1HGCM82633A004352' } });
    await waitFor(() => expect(screen.queryByText(/datos encontrados/i)).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /siguiente/i }));
    fireEvent.change(await screen.findByLabelText('Fecha de entrega'), { target: { value: '2025-01-10' } });
    const photo = new File(['x'], 'acta.jpg', { type: 'image/jpeg' });
    const fileInput = screen.getByLabelText(/acta de entrega/i);
    fireEvent.change(fileInput, { target: { files: [photo] } });
    fireEvent.click(screen.getByRole('button', { name: /siguiente/i }));
    fireEvent.click(await screen.findByRole('button', { name: /registrar entrega/i }));

    await waitFor(() => {
      const postCall = mockAuthFetch.mock.calls.find(([, opts]) => opts && opts.method === 'POST');
      expect(postCall).toBeTruthy();
    });
    const [, postOpts] = mockAuthFetch.mock.calls.find(([, opts]) => opts && opts.method === 'POST');
    const payload = JSON.parse(postOpts.body.get('payload'));
    expect(payload.client.department).toBe('Cundinamarca');
    expect(payload.client.city).toBe('Bogotá');
  });
});
