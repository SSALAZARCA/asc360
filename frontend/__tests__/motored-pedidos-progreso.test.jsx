/** Motored Fase 4 (F1): progress polling of a corrida being calculated (UX-03). */
import React from 'react';
import { render, screen, act } from '@testing-library/react';
import { installFetch, jsonRes, PROGRESO } from './helpers/pedidosFetch';

import ProgresoCorrida from '../components/motored/pedidos/ProgresoCorrida';

const RUTA = 'GET /corridas/c2/progreso';

async function tick(ms) {
  await act(async () => { jest.advanceTimersByTime(ms); });
}

beforeEach(() => {
  jest.useFakeTimers();
  sessionStorage.clear();
  sessionStorage.setItem('motored_token', 'tok');
});
afterEach(() => {
  jest.useRealTimers();
});

describe('ProgresoCorrida', () => {
  it('reads the progress right away and shows "Sucursal 12 de 47"', async () => {
    const calls = installFetch({ [RUTA]: jsonRes(PROGRESO) });
    render(<ProgresoCorrida corridaId="c2" estado="CALCULANDO" />);
    expect(await screen.findByText('Sucursal 12 de 47')).toBeInTheDocument();
    expect(screen.getByText(/Pereira/)).toBeInTheDocument();
    expect(calls).toHaveLength(1);
  });

  it('polls every 3 seconds and follows the numbers', async () => {
    let n = 12;
    const calls = installFetch({ [RUTA]: () => jsonRes({ ...PROGRESO, procesadas: n++ }) });
    render(<ProgresoCorrida corridaId="c2" estado="CALCULANDO" />);
    await screen.findByText('Sucursal 12 de 47');
    await tick(2900);
    expect(calls).toHaveLength(1);
    await tick(200);
    expect(await screen.findByText('Sucursal 13 de 47')).toBeInTheDocument();
    await tick(3000);
    expect(await screen.findByText('Sucursal 14 de 47')).toBeInTheDocument();
    expect(calls).toHaveLength(3);
  });

  it('stops at a terminal state and tells the parent once', async () => {
    const onTerminal = jest.fn();
    const respuestas = [PROGRESO, { ...PROGRESO, estado: 'BORRADOR', procesadas: 47 }];
    const calls = installFetch({ [RUTA]: () => jsonRes(respuestas.shift() || respuestas[0]) });
    render(<ProgresoCorrida corridaId="c2" estado="CALCULANDO" onTerminal={onTerminal} />);
    await screen.findByText('Sucursal 12 de 47');
    await tick(3000);
    await act(async () => {});
    expect(onTerminal).toHaveBeenCalledTimes(1);
    expect(onTerminal.mock.calls[0][0].estado).toBe('BORRADOR');
    await tick(12000);
    expect(calls).toHaveLength(2);
  });

  it('stops polling when it unmounts', async () => {
    const calls = installFetch({ [RUTA]: jsonRes(PROGRESO) });
    const { unmount } = render(<ProgresoCorrida corridaId="c2" estado="CALCULANDO" />);
    await screen.findByText('Sucursal 12 de 47');
    unmount();
    await tick(15000);
    expect(calls).toHaveLength(1);
  });

  it('does not poll a corrida that is not being calculated', async () => {
    const calls = installFetch({});
    render(<ProgresoCorrida corridaId="c1" estado="BORRADOR" />);
    await tick(10000);
    expect(calls).toHaveLength(0);
  });

  it('tells a queued corrida apart from one in progress', async () => {
    installFetch({ 'GET /corridas/c6/progreso': jsonRes({ ...PROGRESO, estado: 'PENDIENTE', procesadas: 0, actual: null }) });
    render(<ProgresoCorrida corridaId="c6" estado="PENDIENTE" />);
    expect(await screen.findByText('En cola')).toBeInTheDocument();
  });

  it('keeps polling after a transient failure', async () => {
    let n = 0;
    const calls = installFetch({
      [RUTA]: () => (++n === 1 ? jsonRes({}, 500) : jsonRes(PROGRESO)),
    });
    render(<ProgresoCorrida corridaId="c2" estado="CALCULANDO" />);
    await act(async () => {});
    await tick(3000);
    expect(await screen.findByText('Sucursal 12 de 47')).toBeInTheDocument();
    expect(calls).toHaveLength(2);
  });

  it('stops for good on a 404 and shows the message', async () => {
    const calls = installFetch({ [RUTA]: jsonRes({ detail: 'Corrida no encontrada.' }, 404) });
    render(<ProgresoCorrida corridaId="c2" estado="CALCULANDO" />);
    expect(await screen.findByText('Corrida no encontrada.')).toBeInTheDocument();
    await tick(12000);
    expect(calls).toHaveLength(1);
  });
});
