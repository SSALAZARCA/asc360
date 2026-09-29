'use client';
/**
 * frontend/components/motored/maestros/HomologadosCell.js
 *
 * "Homologados otras marcas" cell of the Referencias table. A referencia can
 * list ~45 motorcycle models, so the cell never wraps: it shows the first
 * VISIBLE_COUNT models on one line (ellipsis if they still don't fit) plus a
 * `+N` button. Hovering the cell shows every model in a popover; clicking
 * `+N` pins it open so the text can be read or copied. Escape or a click
 * outside closes it. Styles are inline with the shared Motored CSS variables
 * so light and dark themes both work without touching `layout.js`.
 */
import { useEffect, useRef, useState } from 'react';

const VISIBLE_COUNT = 3;

const wrapperStyle = { position: 'relative', display: 'flex', alignItems: 'center', gap: '0.35rem', maxWidth: '260px' };
const textStyle = { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 };
const badgeStyle = {
  flexShrink: 0, cursor: 'pointer', fontSize: '0.7rem', fontWeight: 600, lineHeight: 1.4, padding: '0 6px',
  borderRadius: '999px', border: '1px solid var(--motored-border, #e4e4e7)',
  background: 'var(--motored-surface-alt, #f4f4f5)', color: 'var(--motored-text, #1a1a18)',
};
const popoverStyle = {
  position: 'absolute', top: '100%', left: 0, marginTop: '4px', zIndex: 30, width: 'max-content',
  maxWidth: '420px', maxHeight: '240px', overflowY: 'auto', whiteSpace: 'normal', lineHeight: 1.5,
  padding: '8px 10px', fontSize: '12px', userSelect: 'text', background: 'var(--motored-surface, #ffffff)',
  color: 'var(--motored-text, #1a1a18)', border: '1px solid var(--motored-border, #e4e4e7)',
  borderRadius: 'var(--motored-radius-sm, 6px)', boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
};

// Closes a pinned popover on Escape or on a mousedown outside `ref`.
function useDismiss(active, ref, onClose) {
  useEffect(() => {
    if (!active) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') onClose(true); };
    const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) onClose(false); };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onDown);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onDown);
    };
  }, [active, ref, onClose]);
}

function useHomologadosPopover() {
  const [hovered, setHovered] = useState(false);
  const [pinned, setPinned] = useState(false);
  const wrapperRef = useRef(null);
  const badgeRef = useRef(null);
  const open = hovered || pinned;
  const close = useRef((refocus) => {
    setHovered(false);
    setPinned(false);
    if (refocus) badgeRef.current?.focus();
  }).current;
  useDismiss(open, wrapperRef, close);
  return { open, pinned, setHovered, togglePinned: () => setPinned((p) => !p), wrapperRef, badgeRef };
}

export default function HomologadosCell({ values }) {
  const popover = useHomologadosPopover();
  if (!values?.length) return <em>—</em>;

  const all = values.join(', ');
  const hiddenCount = values.length - VISIBLE_COUNT;
  if (hiddenCount <= 0) return <div style={wrapperStyle}><span style={textStyle} title={all}>{all}</span></div>;

  return (
    <div
      ref={popover.wrapperRef}
      style={wrapperStyle}
      onMouseEnter={() => popover.setHovered(true)}
      onMouseLeave={() => popover.setHovered(false)}
    >
      <span style={textStyle}>{values.slice(0, VISIBLE_COUNT).join(', ')}</span>
      <button
        ref={popover.badgeRef}
        type="button"
        style={badgeStyle}
        aria-label={`Ver los ${values.length} modelos`}
        aria-expanded={popover.pinned}
        onClick={popover.togglePinned}
      >
        +{hiddenCount}
      </button>
      {popover.open && <div role="dialog" aria-label="Homologados otras marcas" style={popoverStyle}>{all}</div>}
    </div>
  );
}
