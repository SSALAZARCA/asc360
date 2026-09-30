'use client';
/** Previous/next controls with "Página X de Y". */
export default function DetractoresPagination({ page, pageSize, total, onChange }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', fontSize: '0.8rem' }}>
      <button type="button" className="motored-btn motored-btn-secondary" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        Anterior
      </button>
      <span>Página {page} de {pages}</span>
      <button type="button" className="motored-btn motored-btn-secondary" disabled={page >= pages} onClick={() => onChange(page + 1)}>
        Siguiente
      </button>
    </div>
  );
}
