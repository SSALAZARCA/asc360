/**
 * Avisos tab, daily asesor report (odd/motored-reporte-diario-asesor, T3b):
 * the three keys with tooltips, the "Estado del envío" panel from
 * GET /reporte-asesor/estado, and "Reenviar reportes a todos los asesores",
 * which asks for confirmation with the number of asesores before calling
 * POST /reporte-asesor/reenviar.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

jest.mock('../lib/motored/api', () => ({
  getReporteAsesorEstado: jest.fn(),
  reenviarReportesAsesores: jest.fn(),
}));

import { getReporteAsesorEstado, reenviarReportesAsesores } from '../lib/motored/api';
import SeccionPanel from '../components/motored/configuracion/SeccionPanel';

const spec = (clave, tipo, valor) => ({
  clave, seccion: 'avisos', grupo: 'OPERACION', tipo, dominio: 'dominio',
  ambito: 'GLOBAL', default: valor, opciones: [], minimo: null, maximo: null,
  minimo_exclusivo: false, campos: [], snapshotted: false,
  efectivo_global: { valor, fuente: 'DEFAULT', vigente_desde: null, parametro_id: null },
  por_sucursal: [], programados: [],
});

const CLAVES = [
  spec('aviso_hora_vispera', 'hora', '16:30'),
  spec('reporte_asesor_envio_activo', 'bool', false),
  spec('reporte_asesor_hora_minima', 'hora', '06:00'),
  spec('reporte_asesor_hora_limite', 'hora', '10:00'),
];

const ESTADO = {
  envio_activo: false,
  hora_limite: '10:00',
  hora_minima: '06:00',
  falta_configuracion: null,
  ultimo_envio: { fecha_datos: '2026-10-05', enviados: 12, fallidos: 1, bloqueados: 2 },
  bloqueados: ['Beto Bloqueado', 'Cami Bloqueada'],
  fecha_disponible: '2026-10-06',
  lista_hoy: true,
  elegibles: 14,
  sin_enlace: ['Dora Sin Enlace'],
  sin_cedula_aprobada: ['Eva Pendiente'],
  sin_telegram: [],
  sin_usuario: ['PEREZ JUAN'],
  sin_presupuesto: 3,
  sin_cedula: 1,
};

function montar(claves = CLAVES) {
  const data = { secciones: [{ seccion: 'avisos', grupos: [{ grupo: 'OPERACION', claves }] }] };
  render(
    <SeccionPanel
      seccion={{ id: 'avisos', label: 'Avisos' }} data={data}
      recargar={jest.fn()} onGuardar={jest.fn(async () => ({}))}
    />,
  );
}

const panel = () => screen.getByRole('region', { name: 'Estado del envío' });

beforeEach(() => {
  jest.clearAllMocks();
  getReporteAsesorEstado.mockResolvedValue(ESTADO);
  reenviarReportesAsesores.mockResolvedValue({ fecha_datos: '2026-10-06', a_enviar: 14 });
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe('Informe diario de los asesores', () => {
  it('shows the three keys with their business wording and tooltips', async () => {
    montar();
    [
      'Enviar cada día por Lore a cada asesor el enlace a su informe',
      'No enviar antes de',
      'Hora límite para enviar',
    ].forEach((t) => expect(screen.getByText(t)).toBeInTheDocument());
    const notas = screen.getAllByRole('note').map((n) => n.getAttribute('aria-label'));
    expect(notas.some((n) => n.includes('se envía igual'))).toBe(true);
    expect(notas.some((n) => n.includes('No se envía antes de esta hora'))).toBe(true);
    await screen.findByText(/14 asesores/);
  });

  it('shows the state of the send', async () => {
    montar();
    const p = await waitFor(panel);
    await within(p).findByText(/14 asesores/);
    expect(within(p).getByText(/05\/10\/2026/)).toBeInTheDocument();
    expect(within(p).getByText(/12 enviados · 1 fallido · 2 bloqueados/)).toBeInTheDocument();
    expect(within(p).getByText(/06\/10\/2026/)).toBeInTheDocument();
    expect(within(p).getByText(/Dora Sin Enlace/)).toBeInTheDocument();
    expect(within(p).getByText(/Eva Pendiente/)).toBeInTheDocument();
    expect(within(p).getByText(/Beto Bloqueado, Cami Bloqueada/)).toBeInTheDocument();
    expect(within(p).getByText(/PEREZ JUAN/)).toBeInTheDocument();
    expect(within(p).getByText(/3 asesores con ventas no tienen presupuesto/)).toBeInTheDocument();
    expect(within(p).getAllByRole('note').length).toBeGreaterThanOrEqual(2);
  });

  it('confirms with the number of asesores and calls the API', async () => {
    const confirmar = jest.spyOn(window, 'confirm').mockReturnValue(true);
    montar();
    const boton = await screen.findByRole('button', { name: 'Reenviar reportes a todos los asesores' });
    await waitFor(() => expect(boton).not.toBeDisabled());
    fireEvent.click(boton);
    expect(confirmar).toHaveBeenCalledWith('Se enviará el enlace a 14 asesores por Lore. ¿Continuar?');
    await waitFor(() => expect(reenviarReportesAsesores).toHaveBeenCalledWith({}));
    expect(await screen.findByRole('status')).toHaveTextContent('Se están enviando 14 informes');
    expect(boton.style.minHeight).toBe('44px');
  });

  it('sends the chosen data date', async () => {
    jest.spyOn(window, 'confirm').mockReturnValue(true);
    montar();
    const fecha = await screen.findByLabelText('Fecha de los datos (opcional)');
    fireEvent.change(fecha, { target: { value: '2026-10-02' } });
    fireEvent.click(await screen.findByRole('button', { name: 'Reenviar reportes a todos los asesores' }));
    await waitFor(() => expect(reenviarReportesAsesores).toHaveBeenCalledWith({ fecha_datos: '2026-10-02' }));
  });

  it('does nothing when the confirmation is cancelled', async () => {
    jest.spyOn(window, 'confirm').mockReturnValue(false);
    montar();
    const boton = await screen.findByRole('button', { name: 'Reenviar reportes a todos los asesores' });
    await waitFor(() => expect(boton).not.toBeDisabled());
    fireEvent.click(boton);
    expect(reenviarReportesAsesores).not.toHaveBeenCalled();
  });

  it('shows the API error of the resend', async () => {
    jest.spyOn(window, 'confirm').mockReturnValue(true);
    reenviarReportesAsesores.mockRejectedValue(new Error('Ya hay un reenvío de reportes en curso.'));
    montar();
    const boton = await screen.findByRole('button', { name: 'Reenviar reportes a todos los asesores' });
    await waitFor(() => expect(boton).not.toBeDisabled());
    fireEvent.click(boton);
    expect(await screen.findByRole('alert')).toHaveTextContent('en curso');
  });

  it('disables the resend and says why when a setting is missing', async () => {
    getReporteAsesorEstado.mockResolvedValue({ ...ESTADO, falta_configuracion: 'Falta configurar LORE_BOT_TOKEN.' });
    montar();
    expect(await screen.findByText('Falta configurar LORE_BOT_TOKEN.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reenviar reportes a todos los asesores' })).toBeDisabled();
  });

  it('does not load the state when the server did not return the keys', () => {
    montar([spec('aviso_hora_vispera', 'hora', '16:30')]);
    expect(getReporteAsesorEstado).not.toHaveBeenCalled();
    expect(screen.queryByRole('region', { name: 'Estado del envío' })).toBeNull();
  });
});
