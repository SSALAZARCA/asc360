/** Motored Fase 4 (F2a): display helpers of the Pedidos screens. */
import { unidades, fechaHora, etiquetaQuiebre, dias, etiquetaEvento, etiquetaMotivoEdicion, etiquetaExclusion } from '../components/motored/pedidos/formato';

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
