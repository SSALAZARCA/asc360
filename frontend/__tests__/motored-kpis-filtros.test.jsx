import { fireEvent, render, screen, within } from '@testing-library/react';
import {
  alternarMes, etiquetaHmcl, etiquetaPeriodo, etiquetaTiendas, mesesDelAnio, presetMeses, resumenPeriodo,
} from '../components/motored/kpis/periodo';
import KpiHeader from '../components/motored/kpis/KpiHeader';
import { OPCIONES } from './helpers/kpisVentasFixture';

const ULTIMO = '2026-07';
const ytd = presetMeses('ytd', ULTIMO);

describe('period presets and label rules', () => {
  it('builds the months of the year of the last month with data', () => {
    expect(mesesDelAnio(ULTIMO)).toHaveLength(12);
    expect(mesesDelAnio(ULTIMO)[0]).toBe('2026-01');
  });

  it('presets: year to date, last quarter and last month', () => {
    expect(ytd).toEqual(['2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06', '2026-07']);
    expect(presetMeses('trimestre', ULTIMO)).toEqual(['2026-05', '2026-06', '2026-07']);
    expect(presetMeses('mes', ULTIMO)).toEqual(['2026-07']);
    expect(presetMeses('trimestre', '2026-02')).toEqual(['2026-01', '2026-02']);
  });

  it('labels: Año corrido, one month, contiguous range and scattered months', () => {
    expect(etiquetaPeriodo(ytd, ULTIMO)).toBe('Año corrido');
    expect(etiquetaPeriodo(['2026-07'], ULTIMO)).toBe('Jul 2026');
    expect(etiquetaPeriodo(['2026-07', '2026-08', '2026-09'], '2026-09')).toBe('Jul – Sep 2026');
    expect(etiquetaPeriodo(['2026-01', '2026-07', '2026-08'], '2026-09')).toBe('Ene, Jul, Ago 2026');
    expect(etiquetaPeriodo([], ULTIMO)).toBe('Elegí meses');
  });

  it('toggles months in order and refuses more than 12', () => {
    expect(alternarMes(['2026-03'], '2026-01')).toEqual(['2026-01', '2026-03']);
    expect(alternarMes(['2026-01', '2026-03'], '2026-01')).toEqual(['2026-03']);
    expect(alternarMes(mesesDelAnio(ULTIMO), '2026-13x')).toHaveLength(12);
  });

  it('summarizes the count with singular and plural', () => {
    expect(resumenPeriodo(1)).toBe('1 mes seleccionado');
    expect(resumenPeriodo(3)).toBe('3 meses seleccionados');
  });

  it('store and HMCL labels', () => {
    const t = OPCIONES.tiendas;
    expect(etiquetaTiendas([], t)).toBe('Toda la red');
    expect(etiquetaTiendas([t[1].id], t)).toBe('Cali Cra 1 Dos');
    expect(etiquetaTiendas([t[0].id, t[1].id], t)).toBe('2 tiendas');
    expect(etiquetaHmcl('incluir')).toBe('Incluir HMCL');
    expect(etiquetaHmcl('solo')).toBe('Solo HMCL');
  });
});

function montar(extra = {}) {
  const onChange = jest.fn();
  const filtros = { meses: ytd, sucursales: [], hmcl: 'incluir', ...extra };
  const view = render(<KpiHeader opciones={OPCIONES} filtros={filtros} onChange={onChange} />);
  return { onChange, ...view };
}

describe('KpiHeader', () => {
  it('shows the title, subtitle and three filter buttons with their labels', () => {
    montar();
    expect(screen.getByRole('heading', { name: "KPI's" })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Año corrido/ })).toHaveAttribute('aria-haspopup', 'dialog');
    expect(screen.getByRole('button', { name: /Toda la red/ })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('button', { name: /Incluir HMCL/ })).toBeInTheDocument();
  });

  it('hides the Período filter and shows the label in its place when asked to', () => {
    render(<KpiHeader opciones={OPCIONES} filtros={{ meses: ytd, sucursales: [], hmcl: 'incluir' }} onChange={jest.fn()} ocultarPeriodo etiquetaPeriodo="Inventario al 30/09/2026" />);
    expect(screen.queryByRole('button', { name: /Año corrido/ })).not.toBeInTheDocument();
    expect(screen.getByText('Inventario al 30/09/2026')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Toda la red/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Incluir HMCL/ })).toBeInTheDocument();
  });

  it('opens the period popover with presets and month chips; months without data are disabled', () => {
    const { onChange } = montar();
    fireEvent.click(screen.getByRole('button', { name: /Año corrido/ }));
    const dialog = screen.getByRole('dialog', { name: 'Elegir período' });
    expect(within(dialog).getByRole('button', { name: 'Año corrido' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(dialog).getByRole('button', { name: 'Ago' })).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Ago' }));
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Último trimestre' }));
    expect(onChange).toHaveBeenCalledWith({ meses: ['2026-05', '2026-06', '2026-07'] });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Ene' }));
    expect(onChange).toHaveBeenLastCalledWith({ meses: ytd.slice(1) });
    expect(within(dialog).getByText('7 meses seleccionados')).toBeInTheDocument();
  });

  it('lets an unavailable month that is already selected be deselected', () => {
    const { onChange } = montar({ meses: ['2026-07', '2026-08'] });
    fireEvent.click(screen.getByRole('button', { name: /Jul – Ago 2026/ }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByRole('button', { name: 'Ago' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Ago' }));
    expect(onChange).toHaveBeenCalledWith({ meses: ['2026-07'] });
  });

  it('presets drop the months without data', () => {
    const opciones = { ...OPCIONES, meses_disponibles: OPCIONES.meses_disponibles.filter((m) => m !== '2026-06') };
    const onChange = jest.fn();
    render(<KpiHeader opciones={opciones} filtros={{ meses: ['2026-07'], sucursales: [], hmcl: 'incluir' }} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /Jul 2026/ }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Último trimestre' }));
    expect(onChange).toHaveBeenCalledWith({ meses: ['2026-05', '2026-07'] });
  });

  it('does not let the last month be unselected', () => {
    const { onChange } = montar({ meses: ['2026-07'] });
    fireEvent.click(screen.getByRole('button', { name: /Jul 2026/ }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Jul' }));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('multi-selects stores, searches by name and goes back to the whole network', () => {
    const { onChange, rerender } = montar();
    fireEvent.click(screen.getByRole('button', { name: /Toda la red/ }));
    const dialog = screen.getByRole('dialog', { name: 'Elegir puntos de venta' });
    expect(within(dialog).getAllByRole('checkbox')).toHaveLength(3);
    fireEvent.change(within(dialog).getByLabelText('Buscar tienda'), { target: { value: 'cali' } });
    expect(within(dialog).getAllByRole('checkbox')).toHaveLength(1);
    fireEvent.click(within(dialog).getByRole('checkbox', { name: /Cali Cra 1 Dos/ }));
    expect(onChange).toHaveBeenCalledWith({ sucursales: [OPCIONES.tiendas[1].id] });
    rerender(<KpiHeader opciones={OPCIONES} filtros={{ meses: ytd, sucursales: [OPCIONES.tiendas[1].id], hmcl: 'incluir' }} onChange={onChange} />);
    expect(screen.getByRole('checkbox', { name: /Cali Cra 1 Dos/ })).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Toda la red' }));
    expect(onChange).toHaveBeenLastCalledWith({ sucursales: [] });
  });

  it('clears the store search when the popover is opened again', () => {
    montar();
    const abrir = () => fireEvent.click(screen.getByRole('button', { name: /Toda la red/ }));
    abrir();
    fireEvent.change(screen.getByLabelText('Buscar tienda'), { target: { value: 'zzz' } });
    expect(screen.getByText('Ninguna tienda coincide.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Listo' }));
    abrir();
    expect(screen.getByLabelText('Buscar tienda')).toHaveValue('');
    expect(screen.getAllByRole('checkbox')).toHaveLength(3);
  });

  it('opens the popover toward the right when aligning it to the right would cut it off on the left', () => {
    const original = Element.prototype.getBoundingClientRect;
    Element.prototype.getBoundingClientRect = function rect() {
      if (this.tagName === 'HEADER') return { left: 300, right: 1500, top: 0, bottom: 0, width: 1200, height: 0 };
      return { left: 320, right: 470, top: 0, bottom: 0, width: 150, height: 0 };
    };
    try {
      montar();
      fireEvent.click(screen.getByRole('button', { name: /Toda la red/ }));
      const dialog = screen.getByRole('dialog', { name: 'Elegir puntos de venta' });
      expect(dialog.style.left).toBe('0px');
      expect(dialog.style.right).toBe('');
    } finally {
      Element.prototype.getBoundingClientRect = original;
    }
  });

  it('picks the HMCL mode with radios', () => {
    const { onChange } = montar();
    fireEvent.click(screen.getByRole('button', { name: /Incluir HMCL/ }));
    const dialog = screen.getByRole('dialog', { name: 'Ventas a HMCL' });
    expect(within(dialog).getByRole('radio', { name: /Incluir HMCL/ })).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(within(dialog).getByRole('radio', { name: /Solo HMCL/ }));
    expect(onChange).toHaveBeenCalledWith({ hmcl: 'solo' });
  });

  it('keeps one popover open at a time and closes with Listo, Escape and outside click', () => {
    montar();
    fireEvent.click(screen.getByRole('button', { name: /Año corrido/ }));
    fireEvent.click(screen.getByRole('button', { name: /Incluir HMCL/ }));
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    expect(screen.getByRole('dialog', { name: 'Ventas a HMCL' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Listo' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /Toda la red/ }));
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /Toda la red/ }));
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
