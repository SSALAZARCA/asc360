/**
 * frontend/components/motored/MotoredTableScroll.js
 *
 * Shared horizontal-scroll container for every Motored data table
 * (odd/motored-responsive-tablet, T2). On a narrow screen the table keeps a
 * sensible minimum width (`.motored-table-scroll > table` in the theme CSS)
 * and scrolls inside this box, so the page itself never scrolls sideways.
 */
export default function MotoredTableScroll({ children }) {
  return (
    <div className="motored-table-scroll" style={{ overflowX: 'auto', maxWidth: '100%' }}>
      {children}
    </div>
  );
}
