import { renderHook, act } from '@testing-library/react';
import buildFooter from '../components/motored/encuesta/buildFooter';
import { buildPayload } from '../components/motored/encuesta/buildPayload';
import useOnlineStatus from '../components/motored/encuesta/useOnlineStatus';

describe('buildPayload', () => {
  it('trims, nulls NS/NR and empty observaciones', () => {
    const payload = buildPayload(
      { cedula: ' 10 ', celular4: ' 2233 ', registroId: 'r', q1: 4, matrix: [1, 2, 3, 4, 5, 'NS'], observaciones: '  ' },
      false
    );
    expect(payload).toMatchObject({
      cedula: '10', celular_ultimos4: '2233', registro_id: 'r', satisfaccion_general: 4,
      p_explicacion_tecnica: 1, p_originalidad_repuestos: null, observaciones: null, autoriza_datos: false,
    });
  });
});

describe('buildFooter', () => {
  const base = (over = {}) => ({
    cedula: '', celular4: '', busy: false, submitCedula: jest.fn(), goBack: jest.fn(), setStep: jest.fn(),
    answers: { q1: null, matrix: Array(6).fill(null), observaciones: '' }, ...over,
  });
  it('gates the cédula and Q1 CTAs', () => {
    expect(buildFooter('cedula', base()).cta.disabled).toBe(true);
    expect(buildFooter('q1', base()).cta.disabled).toBe(true);
    expect(buildFooter('q2', base()).cta.label).toBe('Faltan 6 de 6');
  });
  it('enables the identification CTA only with a cédula and exactly 4 celular digits', () => {
    const cta = (over) => buildFooter('cedula', base(over)).cta.disabled;
    expect(cta({ cedula: '10', celular4: '223' })).toBe(true);
    expect(cta({ cedula: '', celular4: '2233' })).toBe(true);
    expect(cta({ cedula: '10', celular4: '2233', busy: true })).toBe(true);
    expect(cta({ cedula: '10', celular4: '2233' })).toBe(false);
  });
  it('has no footer on end screens', () => {
    expect(buildFooter('closing', base())).toBeUndefined();
  });
});

describe('useOnlineStatus', () => {
  it('follows offline and online events', () => {
    const { result } = renderHook(() => useOnlineStatus());
    expect(result.current).toBe(false);
    act(() => { window.dispatchEvent(new Event('offline')); });
    expect(result.current).toBe(true);
    act(() => { window.dispatchEvent(new Event('online')); });
    expect(result.current).toBe(false);
  });
});
