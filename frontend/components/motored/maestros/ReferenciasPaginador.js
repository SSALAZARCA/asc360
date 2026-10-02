'use client';
/**
 * frontend/components/motored/maestros/ReferenciasPaginador.js
 *
 * Paginator for the Referencias tab (`odd/tasks/motored-referencias-
 * paginacion.md`): previous/next, "Página X de Y", total count and a
 * page-size select. Every `<option>` carries an explicit color, otherwise
 * the text is invisible in the dark theme. `sizes` and `unidad` are optional
 * (the Pedidos line table counts lines in other page sizes). `touch` raises
 * the buttons and the select to the 44 px tablet target (Pedidos only).
 */
export const PAGE_SIZES = [25, 50, 100, 200];

const optionStyle = { color: '#1a1a18' };
const TOUCH = { minHeight: '44px', boxSizing: 'border-box' };
const mutedStyle = { fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' };

export function totalPaginas(total, pageSize) {
  return Math.max(1, Math.ceil(total / pageSize));
}

function PageSizeSelect({ pageSize, sizes, onPageSizeChange, touch }) {
  return (
    <label style={{ ...mutedStyle, display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
      Por página
      <select value={pageSize} style={touch ? TOUCH : undefined} onChange={(e) => onPageSizeChange(Number(e.target.value))}>
        {sizes.map((size) => (
          <option key={size} value={size} style={optionStyle}>{size}</option>
        ))}
      </select>
    </label>
  );
}

export default function ReferenciasPaginador({
  page, pageSize, total, onPageChange, onPageSizeChange, sizes = PAGE_SIZES, unidad = 'referencias', touch = false,
}) {
  const paginas = totalPaginas(total, pageSize);
  const style = touch ? TOUCH : undefined;
  return (
    <nav aria-label={`Paginación de ${unidad}`} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
      <button type="button" className="motored-btn motored-btn-secondary" style={style} disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
        Anterior
      </button>
      <span style={mutedStyle}>Página {page} de {paginas}</span>
      <button type="button" className="motored-btn motored-btn-secondary" style={style} disabled={page >= paginas} onClick={() => onPageChange(page + 1)}>
        Siguiente
      </button>
      <span style={mutedStyle}>{total} {unidad}</span>
      <PageSizeSelect pageSize={pageSize} sizes={sizes} onPageSizeChange={onPageSizeChange} touch={touch} />
    </nav>
  );
}
