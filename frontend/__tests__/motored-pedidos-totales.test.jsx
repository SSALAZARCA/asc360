/**
 * Motored Pedidos: the totals of a whole corrida. Three separate stat boxes
 * (Valor total, Referencias, Unidades) above the tabs of the corrida detail,
 * for real corridas and escenarios, and the same three values as compact
 * columns of the corridas list. A corrida still calculating has no totals
 * and shows a dash.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import {
  installFetch, jsonRes, setSession, D_DETALLE, D_PRUEBA, C_CALCULADA, C_CALCULANDO,
} from './helpers/pedidosFetch';
import { formatCOP } from '../lib/motored/formatCOP';
import TotalesCorrida from '../components/motored/pedidos/TotalesCorrida';
import CorridasTable from '../components/motored/pedidos/CorridasTable';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  useParams: () => ({ id: 'c1' }),
  usePathname: () => '/motored/pedidos/c1',
}));
jest.mock('../components/motored/MotoredSidebar', () => {
  const M = () => <div data-testid="sidebar" />;
  M.displayName = 'M';
  return M;
});

import CorridaDetallePage from '../app/motored/pedidos/[id]/page';

const TOTALES = { valor_total: '12345678.00', referencias: 321, unidades: '2310.00' };
// Testing Library collapses the non-breaking space Intl puts after the sign.
const COP = formatCOP('12345678.00').replace(/\s/g, ' ');
const caja = (nombre) => screen.getByRole('group', { name: nombre });

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
});

describe('TotalesCorrida - the three stat boxes', () => {
  it('renders three separate boxes with the formatted figures', () => {
    render(<TotalesCorrida totales={TOTALES} />);
    expect(within(caja('Valor total')).getByText(COP)).toBeInTheDocument();
    expect(within(caja('Referencias')).getByText('321')).toBeInTheDocument();
    expect(within(caja('Unidades')).getByText('2.310')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('explains each box, and that unpriced referencias add no value', () => {
    render(<TotalesCorrida totales={TOTALES} />);
    const notas = screen.getAllByRole('note').map((n) => n.getAttribute('aria-label'));
    expect(notas).toHaveLength(3);
    expect(notas[0]).toMatch(/Las referencias sin precio no suman al valor/);
    expect(notas[1]).toMatch(/referencias distintas/i);
    expect(notas[2]).toMatch(/unidades/i);
  });

  it('shows a dash in every box while there are no totals', () => {
    render(<TotalesCorrida totales={null} />);
    ['Valor total', 'Referencias', 'Unidades'].forEach((nombre) => {
      expect(within(caja(nombre)).getByText('—')).toBeInTheDocument();
    });
  });

  it('wraps the boxes so they fit a tablet', () => {
    const { container } = render(<TotalesCorrida totales={TOTALES} />);
    expect(container.firstChild).toHaveStyle({ display: 'flex', flexWrap: 'wrap' });
  });
});

describe('corrida detail - totals above the tabs', () => {
  const montar = async (detalle) => {
    setSession('COMPRAS');
    installFetch({ 'GET /corridas/c1': jsonRes(detalle) });
    render(<CorridaDetallePage />);
    await screen.findByRole('tablist');
  };
  const antesDeLasPestanas = () => {
    const tabs = screen.getByRole('tablist');
    const posicion = caja('Valor total').compareDocumentPosition(tabs);
    return Boolean(posicion & Node.DOCUMENT_POSITION_FOLLOWING);
  };

  it('shows the totals of a real corrida before the tabs', async () => {
    await montar({ ...D_DETALLE, totales_corrida: TOTALES });
    expect(within(caja('Valor total')).getByText(COP)).toBeInTheDocument();
    expect(antesDeLasPestanas()).toBe(true);
  });

  it('shows them for an escenario too', async () => {
    await montar({ ...D_PRUEBA, id: 'c1', totales_corrida: TOTALES });
    expect(within(caja('Unidades')).getByText('2.310')).toBeInTheDocument();
  });

  it('shows dashes when the backend sends no totals', async () => {
    await montar({ ...D_DETALLE, totales_corrida: null });
    expect(within(caja('Referencias')).getByText('—')).toBeInTheDocument();
  });
});

describe('corridas list - totals columns', () => {
  beforeEach(() => { setSession('COMPRAS'); installFetch({}); });
  const montar = (corridas) => render(
    <CorridasTable corridas={corridas} onOpen={jest.fn()} onAnular={jest.fn()} onTerminal={jest.fn()} />,
  );

  it('adds the Valor total, Referencias and Unidades columns', () => {
    montar([{ ...C_CALCULADA, totales_corrida: TOTALES }]);
    ['Valor total', 'Referencias', 'Unidades'].forEach((titulo) => {
      expect(screen.getByRole('columnheader', { name: new RegExp(`^${titulo}`) })).toBeInTheDocument();
    });
    const fila = screen.getByText('PED-2026-S40-001').closest('tr');
    expect(within(fila).getByText(COP)).toBeInTheDocument();
    expect(within(fila).getByText('321')).toBeInTheDocument();
    expect(within(fila).getByText('2.310')).toBeInTheDocument();
  });

  it('shows dashes for a corrida without totals', () => {
    montar([{ ...C_CALCULADA, totales_corrida: null }]);
    const fila = screen.getByText('PED-2026-S40-001').closest('tr');
    expect(within(fila).getAllByText('—')).toHaveLength(3);
  });

  it('treats a missing field (an older response) as no totals', () => {
    montar([{ ...C_CALCULANDO }]);
    const fila = screen.getByText('PED-2026-S40-002').closest('tr');
    expect(within(fila).getAllByText('—').length).toBeGreaterThanOrEqual(3);
  });
});
