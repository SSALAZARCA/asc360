'use client';
/** Previous/next controls with "Página X de Y". */
// `touch` raises the buttons to the 44 px tablet target (the Pedidos screens); the others keep their size.
const TOUCH = { minHeight: '44px', boxSizing: 'border-box' };

export default function DetractoresPagination({ page, pageSize, total, onChange, touch = false }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const style = touch ? TOUCH : undefined;
  return (
    <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', fontSize: '0.8rem' }}>
      <button type="button" className="motored-btn motored-btn-secondary" style={style} disabled={page <= 1} onClick={() => onChange(page - 1)}>
        Anterior
      </button>
      <span>Página {page} de {pages}</span>
      <button type="button" className="motored-btn motored-btn-secondary" style={style} disabled={page >= pages} onClick={() => onChange(page + 1)}>
        Siguiente
      </button>
    </div>
  );
}
