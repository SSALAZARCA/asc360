/**
 * "Este archivo reemplaza el mes completo de toda la red": the VENTAS upload
 * checkbox (sent as the form field `reemplaza_mes_completo`) and, before
 * Aplicar, the warning that lists the tiendas whose sales of that month will
 * be deleted, with an explicit "Entiendo" acknowledgement that gates Aplicar.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockSubir = jest.fn();
const mockGetInforme = jest.fn();
const mockAplicar = jest.fn();
const mockGetSinLinea = jest.fn();
const mockVaciado = jest.fn();

jest.mock('../lib/motored/api', () => ({
  ...jest.requireActual('../lib/motored/api'),
  subirCargaMovimiento: (...args) => mockSubir(...args),
  getCarga: jest.fn(),
  descargarPlantillaMovimiento: jest.fn(),
  getInformeCarga: (...args) => mockGetInforme(...args),
  aplicarCarga: (...args) => mockAplicar(...args),
  anularCarga: jest.fn(),
  getReferenciasSinLinea: (...args) => mockGetSinLinea(...args),
  asignarLineaReferencia: jest.fn(),
  asignarLineasReferencias: jest.fn(),
  getParametroVigente: jest.fn(async () => ({ valor: [] })),
  getVaciadoPrevisto: (...args) => mockVaciado(...args),
}));

const mockFetchJson = jest.fn();
jest.mock('../lib/motored/motoredFetch', () => ({
  ...jest.requireActual('../lib/motored/motoredFetch'),
  motoredFetchJson: (...args) => mockFetchJson(...args),
}));

import UploadMovimientoModal from '../components/motored/cargas/UploadMovimientoModal';
import ResumenTab from '../components/motored/cargas/ResumenTab';
import { MOTORED_USER_KEY } from '../lib/motored/motoredFetch';

const { subirCargaMovimiento, getVaciadoPrevisto } = jest.requireActual('../lib/motored/api');

const xlsx = () => new File(['x'], 'ventas.xlsx', {
  type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
});

function abrirModal(tipo) {
  const { container } = render(<UploadMovimientoModal tipo={tipo} label="Ventas" onClose={jest.fn()} />);
  fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [xlsx()] } });
  const desde = container.querySelector('input[type="date"]');
  if (desde) fireEvent.change(desde, { target: { value: '2026-09-01' } });
}

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  mockSubir.mockResolvedValue({ carga_id: 'c1', duplicado_de: null });
});

describe('upload modal -- reemplaza el mes completo', () => {
  it('sends reemplazaMesCompleto true when the VENTAS checkbox is ticked', async () => {
    abrirModal('VENTAS');
    expect(screen.getByText('Borra las ventas de ese mes de las tiendas que no vienen en el archivo.')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Este archivo reemplaza el mes completo de toda la red'));
    fireEvent.click(screen.getByRole('button', { name: 'Subir archivo' }));
    await waitFor(() => expect(mockSubir).toHaveBeenCalledWith(expect.any(File), 'VENTAS', {
      periodoDesde: '2026-09-01', periodoHasta: '2026-09-01', reemplazaMesCompleto: true,
    }));
  });

  it('sends false when the VENTAS checkbox is left alone', async () => {
    abrirModal('VENTAS');
    expect(screen.getByLabelText('Este archivo reemplaza el mes completo de toda la red')).not.toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: 'Subir archivo' }));
    await waitFor(() => expect(mockSubir.mock.calls[0][2].reemplazaMesCompleto).toBe(false));
  });

  it('has no checkbox and sends no flag for other tipos', async () => {
    abrirModal('FACTURAS_PEDIDOS');
    expect(screen.queryByLabelText(/reemplaza el mes completo/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Subir archivo' }));
    await waitFor(() => expect(mockSubir).toHaveBeenCalled());
    expect(mockSubir.mock.calls[0][2]).not.toHaveProperty('reemplazaMesCompleto');
  });
});

describe('api -- reemplaza_mes_completo and vaciado-previsto', () => {
  it('appends the form field only when the flag is given', async () => {
    mockFetchJson.mockResolvedValue({});
    await subirCargaMovimiento(xlsx(), 'VENTAS', { periodoDesde: '2026-09-01', reemplazaMesCompleto: true });
    await subirCargaMovimiento(xlsx(), 'INVENTARIO', { periodoDesde: '2026-09-01' });
    expect(mockFetchJson.mock.calls[0][1].body.get('reemplaza_mes_completo')).toBe('true');
    expect(mockFetchJson.mock.calls[1][1].body.has('reemplaza_mes_completo')).toBe(false);
  });

  it('reads the planned purge of a carga', async () => {
    mockFetchJson.mockResolvedValue([]);
    await getVaciadoPrevisto('c9');
    expect(mockFetchJson).toHaveBeenCalledWith('/cargas/c9/vaciado-previsto');
  });
});

describe('Resumen -- planned purge before Aplicar', () => {
  const INFORME = {
    id: 'carga-1', estado: 'VALIDADO', filas_leidas: 10, filas_validas: 10, filas_rechazadas: 0,
    periodo_desde: '2026-09-01', periodo_hasta: '2026-09-30', log: {}, variacion_pct_vs_carga_anterior: null,
  };
  const VACIADO = [
    { sucursal_id: 's1', nombre: 'Manizales', mes: '2026-09-01', filas_actuales: 120 },
    { sucursal_id: 's2', nombre: 'Pereira', mes: '2026-09-01', filas_actuales: 80 },
  ];
  const AVISO = 'Se van a borrar las ventas de septiembre de 2026 de 2 tiendas que no vienen en este archivo: '
    + 'Manizales, Pereira. Anular esta carga después NO las recupera.';

  async function renderizar() {
    sessionStorage.setItem(MOTORED_USER_KEY, JSON.stringify({ role: 'COMPRAS' }));
    mockGetInforme.mockResolvedValue(INFORME);
    mockGetSinLinea.mockResolvedValue({ sin_linea: [], fuera_de_linea: [], no_encontradas: [] });
    render(<ResumenTab carga={{ id: 'carga-1', tipo: 'VENTAS', estado: 'VALIDADO' }} />);
    await screen.findByText('Todas las referencias del archivo tienen línea.');
  }

  it('warns about the tiendas whose sales are deleted and gates Aplicar on Entiendo', async () => {
    mockVaciado.mockResolvedValue(VACIADO);
    mockAplicar.mockResolvedValue({});
    await renderizar();
    expect(await screen.findByText(AVISO)).toBeInTheDocument();
    const aplicar = screen.getByRole('button', { name: 'Aplicar' });
    expect(aplicar).toBeDisabled();
    fireEvent.click(screen.getByLabelText('Entiendo que se borran esas ventas'));
    expect(aplicar).toBeEnabled();
    fireEvent.click(aplicar);
    await waitFor(() => expect(mockAplicar).toHaveBeenCalledWith('carga-1'));
    expect(mockVaciado).toHaveBeenCalledWith('carga-1');
  });

  it('shows nothing extra and keeps Aplicar enabled when nothing is deleted', async () => {
    mockVaciado.mockResolvedValue([]);
    await renderizar();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Aplicar' })).toBeEnabled());
    expect(screen.queryByText(/Se van a borrar/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Entiendo que se borran esas ventas')).not.toBeInTheDocument();
  });

  it('asks for the acknowledgement when the planned purge cannot be read', async () => {
    mockVaciado.mockRejectedValue(new Error('caído'));
    await renderizar();
    expect(await screen.findByText(/No se pudo verificar si esta carga borra ventas de otras tiendas/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Aplicar' })).toBeDisabled();
    fireEvent.click(screen.getByLabelText('Entiendo que se borran esas ventas'));
    expect(screen.getByRole('button', { name: 'Aplicar' })).toBeEnabled();
  });
});
