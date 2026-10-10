/**
 * Device side of odd/tasks/motored-conteo-codigo-sin-guiones.md: the match
 * key (same examples as backend/tests/motored/test_conteos_codigo_clave.py)
 * and the catalogue lookup by exact code, then by key.
 */
import { claveCodigo } from '../components/motored/conteo-publico/registro';
import { buscarEn, indiceDesde } from '../components/motored/conteo-publico/useCatalogo';

describe('claveCodigo', () => {
  it.each(['94109-12000S', '9410912000S', ' 94109 12000s ', '94109.12000S'])(
    'drops everything outside A-Z and digits: %s', (crudo) => {
      expect(claveCodigo(crudo)).toBe('9410912000S');
    },
  );

  it.each([['', ''], [null, ''], ['--', ''], ['ABC-1/2', 'ABC12'], ['UBI-B7', 'UBIB7']])(
    'edge case %p gives %p', (crudo, esperado) => {
      expect(claveCodigo(crudo)).toBe(esperado);
    },
  );
});

describe('buscarEn', () => {
  const indice = indiceDesde([
    ['94109-12000S', 'Tornillo'], ['AB-12', 'Buje'], ['AB.12', 'Buje largo'], ['UBIB7', 'Raro'],
  ]);

  it('finds the master code from a hyphen-less or spaced scan', () => {
    for (const crudo of ['9410912000S', ' 94109 12000s ', '94109.12000S']) {
      expect(buscarEn(indice, crudo)).toEqual({ codigo: '94109-12000S', nombre: 'Tornillo' });
    }
  });

  it('an exact master code wins over an ambiguous key', () => {
    expect(buscarEn(indice, 'ab.12')).toEqual({ codigo: 'AB.12', nombre: 'Buje largo' });
  });

  it('a key shared by two master codes is ambiguous', () => {
    expect(buscarEn(indice, 'AB12')).toEqual({ ambiguo: ['AB-12', 'AB.12'] });
  });

  it('a location label is never matched by key', () => {
    expect(buscarEn(indice, 'UBI-B7')).toBeNull();
    expect(buscarEn(indice, 'UBIB7')).toEqual({ codigo: 'UBIB7', nombre: 'Raro' });
  });

  it('an unknown code is null', () => {
    expect(buscarEn(indice, 'ZZZ-1')).toBeNull();
  });
});
