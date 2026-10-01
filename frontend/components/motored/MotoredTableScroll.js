/**
 * frontend/components/motored/MotoredTableScroll.js
 *
 * Shared horizontal-scroll container for every Motored data table
 * (odd/motored-responsive-tablet, T2). On a narrow screen the table keeps a
 * sensible minimum width (`.motored-table-scroll > table` in the theme CSS)
 * and scrolls inside this box, so the page itself never scrolls sideways.
 * `maxHeight` (optional) also scrolls vertically inside the box, which lets a
 * sticky header row stay visible on long tables.
 */
export default function MotoredTableScroll({ children, maxHeight }) {
  const vertical = maxHeight ? { maxHeight, overflowY: 'auto' } : {};
  return (
    <div className="motored-table-scroll" style={{ overflowX: 'auto', maxWidth: '100%', ...vertical }}>
      {children}
    </div>
  );
}
