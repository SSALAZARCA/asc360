/**
 * "Ingresos de facturas" tab: who enters each invoice and the fixed values of
 * the ERP template. The tipo "texto" fields keep their leading zeros.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import SeccionPanel from '../components/motored/configuracion/SeccionPanel';
import { SECCIONES } from '../components/motored/configuracion/secciones';

const spec = (clave, tipo, valor, extra = {}) => ({
  clave, seccion: 'ingresos', grupo: 'OPERACION', tipo, dominio: 'dominio',
  ambito: 'GLOBAL', default: valor, opciones: [], minimo: null, maximo: null,
  minimo_exclusivo: false, campos: [], snapshotted: false,
  efectivo_global: { valor, fuente: 'DEFAULT', vigente_desde: null, parametro_id: null },
  por_sucursal: [], programados: [], ...extra,
});

const INGRESOS = [
  spec('ingreso_umbral_referencias_asesor', 'entero', 10),
  spec('ingreso_plantilla_tipo_documento', 'entero', 16),
  spec('ingreso_plantilla_descuento_global', 'decimal', '5'),
  spec('ingreso_plantilla_proveedor_nit', 'entero', 900723988),
  spec('ingreso_plantilla_sucursal_proveedor', 'texto', '001'),
  spec('ingreso_plantilla_comprador', 'entero', 1151943311),
  spec('ingreso_plantilla_descuento_item', 'decimal', '0'),
  spec('ingreso_plantilla_unidad_negocio', 'texto', '003'),
  spec('ingreso_tipos_pedido_excluidos', 'lista', ['GARANTIA25']),
];

function montar() {
  const onGuardar = jest.fn(async () => ({}));
  render(
    <SeccionPanel
      seccion={{ id: 'ingresos', label: 'Ingresos de facturas' }}
      data={{ secciones: [{ seccion: 'ingresos', grupos: [{ grupo: 'OPERACION', claves: INGRESOS }] }] }}
      recargar={jest.fn()} onGuardar={onGuardar}
    />,
  );
  return { onGuardar };
}
const campo = (nombre) => screen.getByText(nombre).closest('section');

describe('Ingresos tab', () => {
  it('is one of the Configuración tabs', () => {
    expect(SECCIONES.find((s) => s.id === 'ingresos')?.label).toBe('Ingresos de facturas');
  });

  it('shows the nine settings with business wording and a tooltip each', () => {
    montar();
    [
      'Máximo de referencias que ingresa el asesor', 'Tipo de documento (ERP)', 'Descuento global %',
      'NIT proveedor', 'Sucursal del proveedor', 'Comprador (cédula)', 'Descuento por ítem %', 'Unidad de negocio',
      'Tipos de pedido que no se ingresan',
    ].forEach((n) => expect(screen.getByText(n)).toBeInTheDocument());
    expect(screen.getAllByRole('note')).toHaveLength(9);
  });

  it('shows a texto value with its leading zeros as a text input', () => {
    montar();
    expect(within(campo('Sucursal del proveedor')).getByRole('textbox')).toHaveValue('001');
    expect(within(campo('Unidad de negocio')).getByRole('textbox')).toHaveValue('003');
  });

  it('saves a texto value as a string and keeps the leading zeros', async () => {
    const { onGuardar } = montar();
    const c = campo('Sucursal del proveedor');
    fireEvent.change(within(c).getByRole('textbox'), { target: { value: '002' } });
    fireEvent.click(within(c).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    expect(onGuardar.mock.calls[0][0]).toMatchObject({
      clave: 'ingreso_plantilla_sucursal_proveedor', valor: '002',
    });
  });

  it('refuses an empty texto value', async () => {
    const { onGuardar } = montar();
    const c = campo('Unidad de negocio');
    fireEvent.change(within(c).getByRole('textbox'), { target: { value: '  ' } });
    fireEvent.click(within(c).getByRole('button', { name: 'Guardar' }));
    expect(await within(c).findByRole('alert')).toHaveTextContent(/código/i);
    expect(onGuardar).not.toHaveBeenCalled();
  });

  it('saves the threshold as an integer', async () => {
    const { onGuardar } = montar();
    const c = campo('Máximo de referencias que ingresa el asesor');
    fireEvent.change(within(c).getByRole('textbox'), { target: { value: '12' } });
    fireEvent.click(within(c).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    expect(onGuardar.mock.calls[0][0]).toMatchObject({ clave: 'ingreso_umbral_referencias_asesor', valor: 12 });
  });

  it('explains which order types are left out of the ingreso process', () => {
    montar();
    expect(campo('Tipos de pedido que no se ingresan')).toHaveTextContent(
      /Facturas con estos tipos de pedido \(ej: GARANTIA25\) no aparecen en Ingresos facturas ni en el aviso del asesor; siguen contando como tránsito\./,
    );
  });

  it('edits the excluded order types as an upper-case list', async () => {
    const { onGuardar } = montar();
    const c = campo('Tipos de pedido que no se ingresan');
    expect(within(c).getByText('GARANTIA25')).toBeInTheDocument();
    fireEvent.change(within(c).getByRole('textbox'), { target: { value: 'otro25' } });
    fireEvent.keyDown(within(c).getByRole('textbox'), { key: 'Enter' });
    fireEvent.click(within(c).getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    expect(onGuardar.mock.calls[0][0]).toMatchObject({
      clave: 'ingreso_tipos_pedido_excluidos', valor: ['GARANTIA25', 'OTRO25'],
    });
  });
});
