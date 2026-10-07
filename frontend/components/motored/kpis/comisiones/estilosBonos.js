/** Responsive rules of the commission rows and the bonus mosaic (inline styles cannot carry media queries). */
export const CSS_BONOS = `
.com-fila { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; }
.com-nombre { flex: 1 1 150px; min-width: 0; }
.com-barras { flex: 4 1 210px; min-width: 0; }
.com-total { flex: 0 0 auto; min-width: 84px; text-align: right; }
.com-tramo { flex: 0 0 56px; }
.bon-mosaico { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
@media (max-width: 1024px) { .bon-mosaico { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 640px) { .bon-mosaico { grid-template-columns: minmax(0, 1fr); } }
`;
