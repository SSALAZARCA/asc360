/**
 * frontend/lib/motored/paginacion.js
 *
 * Adapter between the backend paging (`limite` / `offset`) and the UI paging
 * (`page` 1-based / `pageSize`) used by the shared paginators.
 */
export const aLimiteOffset = (page, pageSize) => ({
  limite: pageSize,
  offset: (page - 1) * pageSize,
});

export const aPagina = ({ total, limite, offset }) => {
  const pageSize = Math.max(1, limite || 1);
  return { page: Math.floor(offset / pageSize) + 1, pageSize, total };
};
