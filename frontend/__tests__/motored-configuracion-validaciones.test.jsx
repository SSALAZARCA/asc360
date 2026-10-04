/**
 * Pure validators of the Indicadores and Comisiones editors. Their messages
 * are the Spanish twin of the backend rules (first tramo at 0, strictly
 * increasing, unique names, semáforo order and 0..200 range, unique NITs).
 */
import {
  validarLista, validarSemaforo, validarTramos,
} from '../components/motored/configuracion/validaciones';

const tramo = (nombre, desde, tasa) => ({ nombre, desde_pct: desde, tasa_pct: tasa });

describe('validarTramos', () => {
  it('accepts the agreed default', () => {
    expect(validarTramos([tramo('BASE', '0', '1.0'), tramo('PRO', '90', '1.5'), tramo('ELITE', '105', '1,8')])).toEqual([]);
  });

  it('asks for at least one tramo', () => {
    expect(validarTramos([])).toEqual(['Agregue al menos un tramo.']);
  });

  it('wants the first tramo to start at 0', () => {
    expect(validarTramos([tramo('A', '5', '1')])).toContain('El primer tramo debe empezar en 0 %.');
  });

  it('wants "desde" to grow strictly from one tramo to the next', () => {
    const msgs = validarTramos([tramo('A', '0', '1'), tramo('B', '90', '1'), tramo('C', '90', '1')]);
    expect(msgs).toContain('Tramo 3: «Desde» debe ser mayor que el del tramo anterior.');
    expect(validarTramos([tramo('A', '0', '1'), tramo('B', '90', '1'), tramo('C', '80', '1')]))
      .toContain('Tramo 3: «Desde» debe ser mayor que el del tramo anterior.');
  });

  it('wants a name and a number in every field', () => {
    expect(validarTramos([tramo('  ', '0', '1')])).toContain('Tramo 1: escriba un nombre.');
    expect(validarTramos([tramo('A', 'x', '1')])).toContain('Tramo 1: «Desde» y «Tasa» necesitan un número.');
    expect(validarTramos([tramo('A', '0', '-1')])).toContain('Tramo 1: «Desde» y «Tasa» necesitan un número.');
  });

  it('rejects repeated names ignoring case and spaces', () => {
    expect(validarTramos([tramo('Pro', '0', '1'), tramo(' PRO ', '90', '1')])).toContain('El nombre «PRO» está repetido.');
  });
});

describe('validarSemaforo', () => {
  it('accepts 90 / 70 and the limits 200 / 0', () => {
    expect(validarSemaforo({ verde_desde: '90', ambar_desde: '70' })).toEqual([]);
    expect(validarSemaforo({ verde_desde: '200', ambar_desde: '0' })).toEqual([]);
  });

  it('wants ámbar below verde', () => {
    expect(validarSemaforo({ verde_desde: '70', ambar_desde: '70' })).toEqual(['«Ámbar desde» debe ser menor que «Verde desde».']);
  });

  it('wants both inside 0 to 200', () => {
    expect(validarSemaforo({ verde_desde: '201', ambar_desde: '70' })).toEqual(['«Verde desde» debe estar entre 0 y 200.']);
  });

  it('wants numbers', () => {
    expect(validarSemaforo({ verde_desde: '', ambar_desde: '70' })).toEqual(['«Verde desde» necesita un número.']);
  });
});

describe('validarLista', () => {
  it('wants a non-empty list', () => {
    expect(validarLista([], {})).toEqual(['Agregue al menos un valor.']);
  });

  it('wants only digits when asked', () => {
    expect(validarLista(['90a'], { digitos: true })).toEqual(['«90a» debe tener sólo dígitos.']);
  });

  it('rejects repeated values when asked', () => {
    expect(validarLista(['9', '9'], { digitos: true, unicos: true })).toEqual(['«9» está repetido.']);
  });
});
