/**
 * frontend/components/motored/MotoredTableScroll.js
 *
 * Shared horizontal-scroll container for every Motored data table
 * (odd/motored-responsive-tablet, T2). On a narrow screen the table keeps a
 * sensible minimum width (`.motored-table-scroll > table` in the theme CSS)
 * and scrolls inside this box, so the page itself never scrolls sideways.
 * `maxHeight` (optional) also scrolls vertically inside the box, which lets a
 * sticky header row stay visible on long tables.
 *
 * The global `::-webkit-scrollbar { width: 6px }` rule (globals.css) sets no
 * height, so Chrome draws the horizontal bar with zero height: wide tables
 * looked cut off with no way to tell they scroll. The rules below give this
 * container an explicit, always visible horizontal bar. They are scoped to
 * `.motored-table-scroll` and live here (not in the theme CSS) on purpose.
 *
 * Hidden header tooltips (visibility: hidden) still take layout space, so the
 * one in the last column pushed the scrollable width about 94px past the
 * table and the final columns could not be reached. Inside this container
 * they only exist while shown.
 */
const SCROLLBAR_CSS = [
  '.motored-table-scroll::-webkit-scrollbar { width: 12px; height: 12px; }',
  '.motored-table-scroll::-webkit-scrollbar-track { background: var(--motored-surface-alt, #f4f4f5); border-radius: 6px; }',
  '.motored-table-scroll::-webkit-scrollbar-thumb { background: var(--motored-text-soft, #8a8a8a); border-radius: 6px; border: 2px solid var(--motored-surface-alt, #f4f4f5); }',
  '.motored-table-scroll::-webkit-scrollbar-thumb:hover { background: var(--motored-text-muted, #5a5a5a); }',
  '.motored-table-scroll .motored-tooltip-text { display: none; }',
  '.motored-table-scroll .motored-tooltip:hover .motored-tooltip-text, .motored-table-scroll .motored-tooltip:focus-visible .motored-tooltip-text { display: block; }',
].join('\n');

export default function MotoredTableScroll({ children, maxHeight }) {
  const vertical = maxHeight ? { maxHeight, overflowY: 'auto' } : {};
  return (
    <>
      <style>{SCROLLBAR_CSS}</style>
      <div className="motored-table-scroll" style={{ overflowX: 'auto', maxWidth: '100%', ...vertical }}>
        {children}
      </div>
    </>
  );
}
