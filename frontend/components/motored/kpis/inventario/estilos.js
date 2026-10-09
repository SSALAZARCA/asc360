import { COLOR } from '../tokens';

/** Responsive grid classes of the Inventario tab (breakpoints taken from the approved board). */
export const CSS_INVENTARIO = `
.inv-tiles{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:14px}
.inv-row{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(280px,1fr);gap:16px}
.inv-half{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.inv-lrow{display:grid;grid-template-columns:minmax(110px,1fr) 110px minmax(0,2fr) 70px 80px 80px;gap:12px;align-items:center}
.inv-link{appearance:none;border:0;background:transparent;font-family:inherit;font-size:inherit;font-weight:700;color:var(--motored-info,#1D4E89);padding:0;min-height:36px;cursor:pointer;text-align:left}
.inv-link:hover{text-decoration:underline}
@media (max-width:1180px){
.inv-tiles{grid-template-columns:repeat(3,minmax(0,1fr))}
.inv-row{grid-template-columns:minmax(0,1fr)}
}
@media (max-width:1024px){
.inv-half{grid-template-columns:minmax(0,1fr)}
}
@media (max-width:640px){
.inv-tiles{grid-template-columns:repeat(2,minmax(0,1fr))}
.inv-lrow{grid-template-columns:minmax(0,1fr) auto 64px}
.inv-lrow .inv-oc{display:none}
.inv-thead{display:none}
}
`;

export const PUNTO = (color, radio = 3) => ({ width: 10, height: 10, borderRadius: radio, background: color });
export const TARJETA_COLUMNA = { display: 'flex', flexDirection: 'column', gap: 14 };
export const SUBTITULO = { margin: '4px 0 0', fontSize: 12.5, color: COLOR.muted };
