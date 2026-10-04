/**
 * Brand-manual colors of the KPI's charts. Each one reads its CSS token from the Motored theme
 * (`app/motored/layout.js`) and falls back to the manual value, so a component also renders
 * outside the layout (tests, previews). Data colors: teal good, amber middle, violet bad.
 * Brand red is NOT here on purpose: it is for the brand and the active tab, never for data.
 */
const token = (nombre, respaldo) => `var(${nombre}, ${respaldo})`;

export const COLOR = {
  good: token('--motored-data-good', '#0F766E'),
  goodSoft: token('--motored-data-good-soft', '#E4F3F1'),
  goodInk: token('--motored-data-good-ink', '#0B5D57'),
  mid: token('--motored-data-mid', '#B45309'),
  midSoft: token('--motored-data-mid-soft', '#FEF3E2'),
  midInk: token('--motored-data-mid-ink', '#8A4104'),
  bad: token('--motored-data-bad', '#6D28A8'),
  badSoft: token('--motored-data-bad-soft', '#F3EAFB'),
  badInk: token('--motored-data-bad-ink', '#5A1F8C'),
  info: token('--motored-info', '#1D4E89'),
  infoSoft: token('--motored-info-soft', '#EAF0F8'),
  ink: token('--motored-gray-900', '#1A1A18'),
  ink2: token('--motored-gray-800', '#3D3D3A'),
  muted: token('--motored-gray-700', '#595954'),
  soft: token('--motored-gray-600', '#6E6E68'),
  gray500: token('--motored-gray-500', '#808080'),
  gray400: token('--motored-gray-400', '#A3A39E'),
  line: token('--motored-gray-300', '#C9C9C6'),
  track: token('--motored-gray-200', '#E4E4E1'),
  wash: token('--motored-gray-100', '#F2F2F0'),
  surface: '#FFFFFF',
};

const CATEGORIAS = ['#0E2A4D', '#1D4E89', '#3570B0', '#5B93CC', '#86B2E0', '#B3CFEE', '#DCE8F6'];

/** The seven blue categories, in order of weight (darkest first). */
export const CATEGORIA = CATEGORIAS.map((hex, i) => token(`--motored-cat-${i + 1}`, hex));

/** Tone -> colors, shared by the gauge, the traffic lights and the chips. */
export const TONO = {
  good: { color: COLOR.good, soft: COLOR.goodSoft, ink: COLOR.goodInk, ring: '#B9DEDA' },
  mid: { color: COLOR.mid, soft: COLOR.midSoft, ink: COLOR.midInk, ring: '#F6D7B0' },
  bad: { color: COLOR.bad, soft: COLOR.badSoft, ink: COLOR.badInk, ring: '#DCC6F0' },
  none: { color: COLOR.gray400, soft: COLOR.wash, ink: COLOR.muted, ring: COLOR.track },
};

/** Medal badge colors by rank: 1, 2, 3 and the rest. */
export const MEDALLA = {
  1: { bg: COLOR.ink, fg: '#FFFFFF' },
  2: { bg: COLOR.muted, fg: '#FFFFFF' },
  3: { bg: COLOR.gray500, fg: '#FFFFFF' },
  rest: { bg: COLOR.track, fg: COLOR.ink2 },
};
