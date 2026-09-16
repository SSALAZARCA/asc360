'use client';
/**
 * frontend/components/motored/InfoTooltip.js
 *
 * Shared help tooltip for Motored screens (sdd/motored-pedidos-cimientos).
 * Standing convention per direct user feedback: any field whose name isn't
 * obvious to a business user (e.g. "SIC", "Días de seguridad") gets one of
 * these next to its label, going forward -- not just for the fields that
 * prompted the request. Presentation lives in `app/motored/layout.js`'s
 * `.motored-tooltip`/`.motored-tooltip-text` classes so every screen shares
 * the same look.
 *
 * Keyboard-accessible: `tabIndex={0}` + `:focus-visible` (in the shared CSS)
 * means it also shows on keyboard focus, not just mouse hover.
 */
import { HelpCircle } from 'lucide-react';

export default function InfoTooltip({ text }) {
  return (
    <span className="motored-tooltip" tabIndex={0} role="note" aria-label={text}>
      <HelpCircle size={13} />
      <span className="motored-tooltip-text">{text}</span>
    </span>
  );
}
