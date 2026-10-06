import { COLOR } from '../tokens';

/** Style of an asesor name that opens her detail: looks like the text, underlined so it reads as a link. */
export const NOMBRE_ENLACE = {
  fontFamily: 'inherit', fontSize: 13, fontWeight: 700, textAlign: 'left', padding: 0, border: 0, background: 'transparent', color: COLOR.ink,
  cursor: 'pointer', textDecoration: 'underline', textDecorationColor: COLOR.line, textUnderlineOffset: 3, maxWidth: '100%',
  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
};
