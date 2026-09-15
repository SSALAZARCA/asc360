/**
 * frontend/app/motored/layout.js
 *
 * Root layout for the entire `/motored/*` route tree (sdd/motored-pedidos-
 * cimientos, Phase 6, design ADR-7). This is where the distinct visual
 * identity lives -- per the user's explicit request ("la ventana de
 * opciones en el menu tambien le quiero dar un diseño y colores diferentes,
 * que solo aplique para las opciones de dicha empresa"), Motored gets its
 * own color scheme (cyan/slate) that never touches asc360's orange
 * (#ff5f33) theme.
 *
 * Deliberately does NOT wrap in <html>/<body> -- this is a NESTED layout
 * under Next's app router; the root `app/layout.js` already owns those.
 *
 * Deliberately does NOT read/check any session here -- auth gating is
 * `motored-layout.js`'s job, applied per-page (mirrors how `admin-layout.js`
 * is applied per-page in asc360, not globally). This file only owns the
 * `.motored-theme` scope so a future re-brand touches ONE file, no routing.
 */
export const metadata = {
  title: 'Motored Pedidos',
};

export default function MotoredRootLayout({ children }) {
  return (
    <div className="motored-theme">
      {children}
      <style jsx global>{`
        .motored-theme {
          --motored-bg: #0a1420;
          --motored-surface: #101d2e;
          --motored-surface-alt: #16273b;
          --motored-border: rgba(148, 197, 255, 0.12);
          --motored-primary: #22d3ee;
          --motored-primary-dark: #0891b2;
          --motored-text: #e6f4ff;
          --motored-text-muted: #7fa3c4;
          --motored-danger: #f87171;
          --motored-warning: #fbbf24;
          --motored-success: #34d399;
          min-height: 100vh;
          background: var(--motored-bg);
          color: var(--motored-text);
        }
      `}</style>
    </div>
  );
}
