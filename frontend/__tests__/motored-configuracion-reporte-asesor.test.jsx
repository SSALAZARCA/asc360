/**
 * Avisos tab, daily asesor report (odd/motored-reporte-diario-asesor, T3b):
 * the three keys with tooltips, the "Estado del envío" panel from
 * GET /reporte-asesor/estado, and "Reenviar reportes a todos los asesores",
 * which asks for confirmation with the number of asesores before calling
 * POST /reporte-asesor/reenviar. T3d: the per-asesor table (estado label
 * with a tooltip, último envío, search) and "Enviar ahora", which confirms
 * and calls POST /reporte-asesor/enviar/{usuario_id}.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

jest.mock('../lib/motored/api', () => ({
  getReporteAsesorEstado: jest.fn(),
  reenviarReportesAsesores: jest.fn(),
  enviarReporteAsesor: jest.fn(),
}));

import { enviarReporteAsesor, getReporteAsesorEstado, reenviarReportesAsesores } from '../lib/motored/api';
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
  asesores: [
    {
      cedula_mask: '****5123', nombre: 'Ana Pérez', tienda: 'Centro', usuario_id: 'u-ana', estado: 'listo',
      ultimo_envio: { en: '2026-10-06T13:05:00+00:00', estado: 'enviado' }, puede_enviar: true,
    },
    {
      cedula_mask: '****1001', nombre: 'PEREZ JUAN', tienda: 'Norte', usuario_id: null, estado: 'sin_usuario',
      ultimo_envio: null, puede_enviar: false,
    },
    {
      cedula_mask: '****2002', nombre: 'Dora Sin Enlace', tienda: 'Bogotá Sur', usuario_id: 'u-dora',
      estado: 'sin_enlace', ultimo_envio: null, puede_enviar: false,
    },
    {
      cedula_mask: '****3003', nombre: 'Eva Pendiente', tienda: 'Centro', usuario_id: 'u-eva',
      estado: 'cedula_pendiente', ultimo_envio: null, puede_enviar: false,
    },
    {
      cedula_mask: '****4004', nombre: 'Beto Bloqueado', tienda: 'Norte', usuario_id: 'u-beto', estado: 'bloqueado',
      ultimo_envio: { en: '2026-10-05T12:00:00+00:00', estado: 'bloqueado' }, puede_enviar: false,
    },
  ],
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
    expect(within(p).getByText(/3 asesores con ventas no tienen presupuesto/)).toBeInTheDocument();
    expect(within(p).getByText(/1 vendedor con ventas no tiene cédula/)).toBeInTheDocument();
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

describe('Tabla de envío por asesor', () => {
  const tabla = async () => {
    montar();
    return screen.findByRole('table', { name: 'Envío por asesor' });
  };
  const filaDe = (t, nombre) => within(t).getByText(nombre).closest('tr');

  it('renders one row per asesor with the Spanish estado and the last send', async () => {
    const t = await tabla();
    expect(within(t).getAllByRole('row')).toHaveLength(ESTADO.asesores.length + 1);
    ['Asesor', 'Tienda', 'Estado', 'Último envío'].forEach((c) => (
      expect(within(t).getByRole('columnheader', { name: c })).toBeInTheDocument()));
    expect(within(filaDe(t, 'Ana Pérez')).getByText('Listo')).toBeInTheDocument();
    expect(within(filaDe(t, 'Ana Pérez')).getByText('06/10 08:05 · Enviado')).toBeInTheDocument();
    expect(within(filaDe(t, 'PEREZ JUAN')).getByText('Sin usuario en Lore')).toBeInTheDocument();
    expect(within(filaDe(t, 'Dora Sin Enlace')).getByText('Sin enlace')).toBeInTheDocument();
    expect(within(filaDe(t, 'Eva Pendiente')).getByText('Cédula pendiente')).toBeInTheDocument();
    expect(within(filaDe(t, 'Beto Bloqueado')).getByText('Bloqueó a Lore')).toBeInTheDocument();
    expect(within(filaDe(t, 'Beto Bloqueado')).getByText('05/10 07:00 · Bloqueado')).toBeInTheDocument();
    expect(within(filaDe(t, 'Ana Pérez')).getByText('****5123')).toBeInTheDocument();
    const ayudas = within(t).getAllByRole('note').map((n) => n.getAttribute('aria-label'));
    expect(ayudas.some((a) => a.includes('Gestión de usuarios'))).toBe(true);
    expect(ayudas.some((a) => a.includes('registrarse en Lore'))).toBe(true);
  });

  it('scrolls inside its own container', async () => {
    const t = await tabla();
    expect(t.parentElement.style.overflowX).toBe('auto');
    expect(t.parentElement.style.maxWidth).toBe('100%');
  });

  it('filters by asesor or tienda, ignoring accents and case', async () => {
    const t = await tabla();
    const buscar = screen.getByLabelText('Buscar asesor o tienda');
    fireEvent.change(buscar, { target: { value: 'perez' } });
    expect(within(t).getAllByRole('row')).toHaveLength(3);
    fireEvent.change(buscar, { target: { value: 'BOGOTA' } });
    expect(within(t).getAllByRole('row')).toHaveLength(2);
    expect(within(t).getByText('Dora Sin Enlace')).toBeInTheDocument();
    fireEvent.change(buscar, { target: { value: 'nadie' } });
    expect(screen.getByText('Ningún asesor coincide con la búsqueda.')).toBeInTheDocument();
  });

  it('disables "Enviar ahora" and says what is missing', async () => {
    const t = await tabla();
    const boton = within(t).getByRole('button', { name: 'Enviar ahora a Dora Sin Enlace' });
    expect(boton).toBeDisabled();
    expect(boton).toHaveAttribute('title', expect.stringContaining('genérelo en Gestión de usuarios'));
    expect(within(t).getByRole('button', { name: 'Enviar ahora a Ana Pérez' })).not.toBeDisabled();
  });

  it('disables every send when a setting is missing', async () => {
    getReporteAsesorEstado.mockResolvedValue({ ...ESTADO, falta_configuracion: 'Falta configurar LORE_BOT_TOKEN.' });
    const t = await tabla();
    const boton = within(t).getByRole('button', { name: 'Enviar ahora a Ana Pérez' });
    expect(boton).toBeDisabled();
    expect(boton).toHaveAttribute('title', 'Falta configurar LORE_BOT_TOKEN.');
  });

  it('confirms, calls the API, shows the result and reloads', async () => {
    const confirmar = jest.spyOn(window, 'confirm').mockReturnValue(true);
    enviarReporteAsesor.mockResolvedValue({ estado: 'enviado', detalle: 'Informe enviado a Ana Pérez por Lore.' });
    const t = await tabla();
    fireEvent.click(within(t).getByRole('button', { name: 'Enviar ahora a Ana Pérez' }));
    expect(confirmar).toHaveBeenCalledWith('¿Enviar ahora el informe a Ana Pérez por Lore?');
    await waitFor(() => expect(enviarReporteAsesor).toHaveBeenCalledWith('u-ana', {}));
    expect(await within(t).findByRole('status')).toHaveTextContent('Informe enviado a Ana Pérez por Lore.');
    await waitFor(() => expect(getReporteAsesorEstado).toHaveBeenCalledTimes(2));
  });

  it('sends the chosen data date', async () => {
    jest.spyOn(window, 'confirm').mockReturnValue(true);
    enviarReporteAsesor.mockResolvedValue({ estado: 'enviado', detalle: 'ok' });
    const t = await tabla();
    fireEvent.change(screen.getByLabelText('Fecha de los datos (opcional)'), { target: { value: '2026-10-02' } });
    fireEvent.click(within(t).getByRole('button', { name: 'Enviar ahora a Ana Pérez' }));
    await waitFor(() => expect(enviarReporteAsesor).toHaveBeenCalledWith('u-ana', { fecha_datos: '2026-10-02' }));
  });

  it('does nothing when the confirmation is cancelled', async () => {
    jest.spyOn(window, 'confirm').mockReturnValue(false);
    const t = await tabla();
    fireEvent.click(within(t).getByRole('button', { name: 'Enviar ahora a Ana Pérez' }));
    expect(enviarReporteAsesor).not.toHaveBeenCalled();
  });

  it('shows the API error in the row', async () => {
    jest.spyOn(window, 'confirm').mockReturnValue(true);
    enviarReporteAsesor.mockRejectedValue(new Error('Telegram no aceptó el mensaje.'));
    const t = await tabla();
    fireEvent.click(within(t).getByRole('button', { name: 'Enviar ahora a Ana Pérez' }));
    expect(await within(t).findByRole('alert')).toHaveTextContent('Telegram no aceptó el mensaje.');
  });

  it('says so when there are no asesores with sales', async () => {
    getReporteAsesorEstado.mockResolvedValue({ ...ESTADO, asesores: [] });
    montar();
    expect(await screen.findByText('No hay asesores con ventas para esa fecha.')).toBeInTheDocument();
  });
});
