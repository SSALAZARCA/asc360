'use client';
/**
 * frontend/components/motored/ventas-perdidas/VentasPerdidasFilters.js
 *
 * sdd/motored-ventas-perdidas-panel, Phase 7 (design D6). Pure controlled
 * component -- mirrors `CargasHistoryTable.js`'s `Filtros` shape (the caller
 * owns `filtros` state; this component only renders it and reports changes
 * up via `setFiltros`). The 30-day default itself lives in
 * `useVentasPerdidas.js` (via `fechaDefaults.js`), not here.
 *
 * Spec "Deactivated sucursal or asesor does not restrict visibility or
 * action": both dropdowns list EVERY sucursal/asesor, active or not -- an
 * inactive one is labelled "(inactiva)"/"(inactivo)", never hidden or
 * disabled. Every `<option>` gets an explicit style (dark-theme rule, see
 * `feedback_select_option_style.md`).
 */
const labelStyle = { display: 'flex', flexDirection: 'column', fontSize: '0.7rem', color: 'var(--motored-text-muted, #5a5a5a)' };
const optionStyle = { color: '#1a1a18' };

export default function VentasPerdidasFilters({ filtros, setFiltros, sucursales, asesores }) {
  return (
    <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
      <label style={labelStyle}>
        Desde
        <input type="date" value={filtros.desde} onChange={(e) => setFiltros({ ...filtros, desde: e.target.value })} />
      </label>
      <label style={labelStyle}>
        Hasta
        <input type="date" value={filtros.hasta} onChange={(e) => setFiltros({ ...filtros, hasta: e.target.value })} />
      </label>
      <label style={labelStyle}>
        Sucursal
        <select value={filtros.sucursalId} onChange={(e) => setFiltros({ ...filtros, sucursalId: e.target.value })}>
          <option value="" style={optionStyle}>Todas</option>
          {sucursales.map((s) => (
            <option key={s.id} value={s.id} style={optionStyle}>
              {s.nombre}{!s.activa ? ' (inactiva)' : ''}
            </option>
          ))}
        </select>
      </label>
      <label style={labelStyle}>
        Asesor
        <select value={filtros.usuarioId} onChange={(e) => setFiltros({ ...filtros, usuarioId: e.target.value })}>
          <option value="" style={optionStyle}>Todos</option>
          {asesores.map((a) => (
            <option key={a.id} value={a.id} style={optionStyle}>
              {a.nombre}{!a.activo ? ' (inactivo)' : ''}
            </option>
          ))}
        </select>
      </label>
      <label style={labelStyle}>
        Estado
        <select value={filtros.estado} onChange={(e) => setFiltros({ ...filtros, estado: e.target.value })}>
          <option value="" style={optionStyle}>Todas</option>
          <option value="ACTIVA" style={optionStyle}>Activa</option>
          <option value="ANULADA" style={optionStyle}>Anulada</option>
        </select>
      </label>
    </div>
  );
}
