/**
 * frontend/app/motored/layout.js
 *
 * Root layout for the entire `/motored/*` route tree (sdd/motored-pedidos-
 * cimientos, Phase 6, design ADR-7). This is where the distinct visual
 * identity lives -- per the user's explicit request ("la ventana de
 * opciones en el menu tambien le quiero dar un diseño y colores diferentes,
 * que solo aplique para las opciones de dicha empresa"), Motored gets its
 * own color scheme that never touches asc360's orange (#ff5f33) theme.
 *
 * Tokens sourced from the REAL Motored brand, not invented:
 * - `Brief_1_Color_y_Tipografia.md` (Motored's own brand manual excerpt):
 *   Rojo Motored #E20714, Negro Motored #1A1A18, gris #808080, blanco.
 * - `Pedidos Motored - Sistema de diseno.html` (the design-system reference
 *   for THIS specific app, in the same folder as the spec): resolves the
 *   manual's raw colors into an accessible, cohesive UI palette (light
 *   surfaces, a refined text-gray scale, brand red reserved for identity/
 *   primary action, a SEPARATE darker red for error/danger so an alert
 *   is never visually confused with the Motored logo -- the exact
 *   "el rojo de marca es también el color de malo" problem the brand brief
 *   calls out) and typography (Mulish body copy, IBM Plex Mono for
 *   tabular/numeric data).
 *
 * Deliberately does NOT wrap in <html>/<body> -- this is a NESTED layout
 * under Next's app router; the root `app/layout.js` already owns those.
 *
 * Deliberately does NOT read/check any session here -- auth gating is
 * `motored-layout.js`'s job, applied per-page (mirrors how `admin-layout.js`
 * is applied per-page in asc360, not globally). This file only owns the
 * `.motored-theme` scope so a future re-brand touches ONE file, no routing.
 *
 * Deliberately does NOT use `<style jsx>` (styled-jsx): that requires a
 * Client Component, which would force `export const metadata` (Server-
 * Component-only, needed for the browser tab title) out of this file. A
 * plain `<style>` tag with a raw CSS string is valid, static, and needs no
 * client-side runtime -- this stylesheet has zero interactivity.
 */
import { Mulish, IBM_Plex_Mono } from 'next/font/google';

const mulish = Mulish({ subsets: ['latin'], weight: ['500', '800'], variable: '--motored-font-body' });
const plexMono = IBM_Plex_Mono({ subsets: ['latin'], weight: ['500', '600'], variable: '--motored-font-mono' });

export const metadata = {
  title: 'Motored Pedidos',
};

const themeCss = `
        .motored-theme {
          --motored-brand: #e20714;
          --motored-brand-dark: #b00510;
          --motored-bg: #f7f7f8;
          --motored-surface: #ffffff;
          --motored-surface-alt: #f4f4f5;
          --motored-border: #e4e4e7;
          --motored-primary: var(--motored-brand);
          --motored-primary-dark: var(--motored-brand-dark);
          --motored-text: #1a1a18;
          --motored-text-muted: #5a5a5a;
          --motored-danger: #c0392b;
          --motored-danger-bg: #fdf3f4;
          --motored-warning: #d97706;
          --motored-success: #15803d;
          min-height: 100vh;
          background: var(--motored-bg);
          color: var(--motored-text);
          font-family: var(--motored-font-body), 'Mulish', system-ui, sans-serif;
        }
        .motored-theme code,
        .motored-theme .motored-mono {
          font-family: var(--motored-font-mono), 'IBM Plex Mono', monospace;
          font-variant-numeric: tabular-nums;
        }
      `;

export default function MotoredRootLayout({ children }) {
  return (
    <div className={`motored-theme ${mulish.variable} ${plexMono.variable}`}>
      {children}
      <style>{themeCss}</style>
    </div>
  );
}
