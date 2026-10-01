/** Motored Fase 4 (F2a): display helpers of the Pedidos screens. */
import { unidades, fechaHora, etiquetaQuiebre, dias, etiquetaEvento, etiquetaMotivoEdicion, etiquetaExclusion, valorCompacto, abreviarTienda, deltaConSigno, direccionDelta, deltaCOP } from '../components/motored/pedidos/formato';

describe('unidades', () => {
  it('drops the decimals of a whole quantity and groups thousands (es-CO)', () => {
    expect(unidades('1010.00')).toBe('1.010');
    expect(unidades('48.00')).toBe('48');
  });

  it('keeps up to two decimals when the quantity has them', () => {
    expect(unidades('12.50')).toBe('12,5');
  });

  it('renders a dash for a missing or non-numeric value', () => {
    expect(unidades(null)).toBe('—');
    expect(unidades('abc')).toBe('—');
  });
});

describe('fechaHora', () => {
  it('shows day/month/year and the hour without any time-zone shift', () => {
    expect(fechaHora('2026-10-02T09:15:00')).toBe('02/10/2026 09:15');
  });

  it('shows only the date when the value has no time', () => {
    expect(fechaHora('2026-10-02')).toBe('02/10/2026');
  });

  it('renders a dash for an empty value', () => {
    expect(fechaHora(null)).toBe('—');
  });
});

describe('etiquetaQuiebre', () => {
  it('translates the engine states to Spanish business wording', () => {
    expect(etiquetaQuiebre('QUIEBRE_TOTAL')).toBe('Quiebre total');
    expect(etiquetaQuiebre('BAJO_MINIMO')).toBe('Bajo mínimo');
  });

  it('falls back to the raw value for an unknown state and a dash for none', () => {
    expect(etiquetaQuiebre('NUEVO')).toBe('NUEVO');
    expect(etiquetaQuiebre(null)).toBe('—');
  });
});

describe('dias', () => {
  it('uses the singular for one day and the plural otherwise', () => {
    expect(dias(1)).toBe('1 día');
    expect(dias(3)).toBe('3 días');
    expect(dias(0)).toBe('0 días');
  });
});

describe('labels of the audit trail', () => {
  it('names the tienda pedido events', () => {
    expect(etiquetaEvento('CERRADO')).toBe('Cerrado');
    expect(etiquetaEvento('REABIERTO')).toBe('Reabierto');
    expect(etiquetaEvento('ENVIO_CORREGIDO')).toBe('Número de orden corregido');
    expect(etiquetaEvento('OTRO')).toBe('OTRO');
  });

  it('names the reason of a line edit', () => {
    expect(etiquetaMotivoEdicion('MANUAL')).toBe('Manual');
    expect(etiquetaMotivoEdicion('RECORTE_PRESUPUESTO')).toBe('Recorte por presupuesto');
  });

  it('names why a line is excluded', () => {
    expect(etiquetaExclusion('SUSTITUIDA')).toBe('Sustituida');
    expect(etiquetaExclusion('INACTIVA_SIN_REEMPLAZO')).toBe('Inactiva sin reemplazo');
  });
});

describe('valorCompacto (a value that must fit a 64 px matrix column)', () => {
  it('shows millions with one decimal and a comma (es-CO)', () => {
    expect(valorCompacto('5400000.00')).toBe('5,4 M');
    expect(valorCompacto('11100000.00')).toBe('11,1 M');
    expect(valorCompacto('3000000.00')).toBe('3 M');
  });

  it('shows thousands as "mil" and small amounts as they are', () => {
    expect(valorCompacto('450000.00')).toBe('450 mil');
    expect(valorCompacto('1500.00')).toBe('1,5 mil');
    expect(valorCompacto('950.00')).toBe('950');
  });

  it('renders a dash for a missing or non-numeric value and 0 for zero', () => {
    expect(valorCompacto(null)).toBe('—');
    expect(valorCompacto('abc')).toBe('—');
    expect(valorCompacto('0.00')).toBe('0');
  });
});

describe('abreviarTienda', () => {
  it('keeps a name of up to 10 characters whole', () => {
    expect(abreviarTienda('Manizales')).toBe('Manizales');
    expect(abreviarTienda('Bucaramang')).toBe('Bucaramang');
  });

  it('cuts a longer name to 10 characters and adds an ellipsis', () => {
    expect(abreviarTienda('Villavicencio')).toBe('Villavicen…');
    expect(abreviarTienda('Bucaramanga')).toBe('Bucaramang…');
  });

  it('copes with a missing name', () => {
    expect(abreviarTienda(null)).toBe('');
  });
});

describe('deltaConSigno', () => {
  it('writes the plus sign of an increase, the minus of a decrease and a bare zero', () => {
    expect(deltaConSigno('12.00')).toBe('+12');
    expect(deltaConSigno('-10.00')).toBe('-10');
    expect(deltaConSigno('0.00')).toBe('0');
  });

  it('never writes a negative zero', () => {
    expect(deltaConSigno('-0.00')).toBe('0');
    expect(deltaCOP('-0.00')).toMatch(/^\$\s?0$/);
  });

  it('groups thousands, keeps decimals and renders a dash for a missing value', () => {
    expect(deltaConSigno('1250.00')).toBe('+1.250');
    expect(deltaConSigno('-0.50')).toBe('-0,5');
    expect(deltaConSigno(null)).toBe('—');
    expect(deltaConSigno('abc')).toBe('—');
  });
});

describe('direccionDelta', () => {
  it('says whether the scenario asks for more, less or the same', () => {
    expect(direccionDelta('12.00')).toBe('sube');
    expect(direccionDelta('-10.00')).toBe('baja');
    expect(direccionDelta('0.00')).toBe('igual');
    expect(direccionDelta(null)).toBe('igual');
  });
});

describe('deltaCOP', () => {
  it('writes a signed peso difference', () => {
    expect(deltaCOP('120000.00')).toMatch(/^\+\$\s?120\.000$/);
    expect(deltaCOP('-90000.00')).toMatch(/^-\$\s?90\.000$/);
    expect(deltaCOP('0.00')).toMatch(/^\$\s?0$/);
    expect(deltaCOP(null)).toBe('—');
  });
});
