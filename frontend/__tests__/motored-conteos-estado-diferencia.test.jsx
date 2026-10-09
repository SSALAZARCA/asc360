/**
 * The panel's reconteo pill must agree with the closed result's
 * "Confirmada"/"Corregida": a finished reconteo is confirmed only when it
 * keeps the sign of the round-1 difference (a zero or a flipped sign is a
 * correction).
 */
import { estadoDiferencia } from '../components/motored/inventarios/DiferenciaFila';

const UMBRALES = { reconteo: '100000', critico: '500000' };
const terminado = (sistema, ronda1, diferencia) => ({
  sistema: String(sistema), contado_ronda1: String(ronda1), diferencia: String(diferencia),
  reconteo: { estado: 'TERMINADO' },
});

describe('estadoDiferencia for a finished reconteo', () => {
  it('confirms when the reconteo keeps the sign of the round-1 difference', () => {
    expect(estadoDiferencia(terminado(10, 4, -3), UMBRALES)[0]).toBe('Confirmada en reconteo');
  });

  it('corrects when the reconteo leaves no difference', () => {
    expect(estadoDiferencia(terminado(10, 4, 0), UMBRALES)[0]).toBe('Corregida en reconteo');
  });

  it('corrects when the reconteo flips the sign of the difference', () => {
    expect(estadoDiferencia(terminado(10, 4, 2), UMBRALES)[0]).toBe('Corregida en reconteo');
  });
});
