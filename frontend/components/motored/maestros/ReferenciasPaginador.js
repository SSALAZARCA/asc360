'use client';
/**
 * frontend/components/motored/maestros/ReferenciasPaginador.js
 *
 * Paginator for the Referencias tab (`odd/tasks/motored-referencias-
 * paginacion.md`): previous/next, "Página X de Y", total count and a
 * page-size select. Every `<option>` carries an explicit color, otherwise
 * the text is invisible in the dark theme.
 */
export const PAGE_SIZES = [25, 50, 100, 200];

const optionStyle = { color: '#1a1a18' };
const mutedStyle = { fontSize: '0.75rem', color: 'var(--motored-text-muted, #5a5a5a)' };

export function totalPaginas(total, pageSize) {
  return Math.max(1, Math.ceil(total / pageSize));
}

function PageSizeSelect({ pageSize, onPageSizeChange }) {
  return (
    <label style={{ ...mutedStyle, display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
      Por página
      <select value={pageSize} onChange={(e) => onPageSizeChange(Number(e.target.value))}>
        {PAGE_SIZES.map((size) => (
          <option key={size} value={size} style={optionStyle}>{size}</option>
        ))}
      </select>
    </label>
  );
}

export default function ReferenciasPaginador({ page, pageSize, total, onPageChange, onPageSizeChange }) {
  const paginas = totalPaginas(total, pageSize);
  return (
    <nav aria-label="Paginación de referencias" style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
      <button type="button" className="motored-btn motored-btn-secondary" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
        Anterior
      </button>
      <span style={mutedStyle}>Página {page} de {paginas}</span>
      <button type="button" className="motored-btn motored-btn-secondary" disabled={page >= paginas} onClick={() => onPageChange(page + 1)}>
        Siguiente
      </button>
      <span style={mutedStyle}>{total} referencias</span>
      <PageSizeSelect pageSize={pageSize} onPageSizeChange={onPageSizeChange} />
    </nav>
  );
}
