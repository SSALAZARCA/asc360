/**
 * Offline queue rules of the pair counting screen (lib/motored/conteoCola.js).
 */
import {
  LOTE_MAXIMO, aPayload, aplicarRespuesta, guardarCola, leerCola, nuevoId, retrasoReintento,
  siguienteEnvio,
} from '../lib/motored/conteoCola';

const lectura = (n) => ({
  op: 'lectura', id: `id-${n}`, codigo_leido: `C${n}`, cantidad: 1, leida_en: '2026-10-09T10:00:00Z',
  metodo: 'ESCANER', ubicacion: 'A3', descripcion: 'X',
});

describe('conteoCola', () => {
  it('sends at most 100 readings per batch', () => {
    const items = Array.from({ length: 250 }, (_, n) => lectura(n));
    const envio = siguienteEnvio(items);
    expect(LOTE_MAXIMO).toBe(100);
    expect(envio.tipo).toBe('lecturas');
    expect(envio.items).toHaveLength(100);
    expect(envio.items[0].id).toBe('id-0');
  });

  it('stops a batch at a void and sends the void alone when it is first', () => {
    const anular = { op: 'anular', id: 'id-0', codigo: 'C0', cantidad: 1, ubicacion: 'A3' };
    expect(siguienteEnvio([lectura(1), anular, lectura(2)]).items).toHaveLength(1);
    expect(siguienteEnvio([anular, lectura(2)])).toEqual({ tipo: 'anular', items: [anular] });
    expect(siguienteEnvio([])).toBeNull();
  });

  it('strips local fields from the payload', () => {
    expect(aPayload({ ...lectura(1), forzar_desconocido: true, reconteo_id: 'r1' })).toEqual({
      id: 'id-1', codigo_leido: 'C1', cantidad: 1, leida_en: '2026-10-09T10:00:00Z', metodo: 'ESCANER',
      forzar_desconocido: true, reconteo_id: 'r1',
    });
  });

  it('sends the location stamped at scan time, and nothing for an old unstamped reading', () => {
    expect(aPayload({ ...lectura(1), ubicacion_codigo: 'B7' })).toEqual({
      id: 'id-1', codigo_leido: 'C1', cantidad: 1, leida_en: '2026-10-09T10:00:00Z', metodo: 'ESCANER',
      ubicacion_codigo: 'B7',
    });
    expect(aPayload(lectura(1))).not.toHaveProperty('ubicacion_codigo');
  });

  it('removes accepted, duplicated, unknown and rejected ids and keeps the rest', () => {
    const items = [lectura(1), lectura(2), lectura(3), lectura(4), lectura(5)];
    const enviados = items.slice(0, 4);
    const r = aplicarRespuesta(items, enviados, {
      aceptadas: ['id-1'], duplicadas: ['id-2'], desconocidos: [{ id: 'id-3', codigo: 'C3' }],
      rechazadas: [{ id: 'id-4', motivo: 'RONDA_CERRADA' }],
    });
    expect(r.items.map((i) => i.id)).toEqual(['id-5']);
    expect(r.hechos.map((i) => i.id)).toEqual(['id-1', 'id-2']);
    expect(r.desconocidos.map((i) => i.id)).toEqual(['id-3']);
    expect(r.rechazadas).toEqual([{ item: items[3], motivo: 'RONDA_CERRADA' }]);
  });

  it('backs off exponentially up to 30 s', () => {
    expect(retrasoReintento(0)).toBe(1500);
    expect(retrasoReintento(1)).toBe(3000);
    expect(retrasoReintento(2)).toBe(6000);
    expect(retrasoReintento(10)).toBe(30000);
  });

  it('persists per slug and survives garbage', () => {
    guardarCola('s1', { sesionId: 'ses', items: [lectura(1)] }, localStorage);
    expect(leerCola('s1', localStorage)).toEqual({ sesionId: 'ses', items: [lectura(1)] });
    guardarCola('s1', { sesionId: 'ses', items: [] }, localStorage);
    expect(localStorage.getItem('motored_conteo_cola:s1')).toBeNull();
    localStorage.setItem('motored_conteo_cola:s2', '{roto');
    expect(leerCola('s2', localStorage)).toEqual({ sesionId: null, items: [] });
  });

  it('makes v4 uuids', () => {
    expect(nuevoId()).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  });
});
