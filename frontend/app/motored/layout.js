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
 * Tokens sourced from the REAL Motored brand, not invented -- confirmed by
 * actually rendering `Pedidos Motored - Sistema de diseno.html` (a JS-bundled
 * Claude Design canvas export that cannot be read as plain text; screenshotted
 * with a locally-installed headless Chrome to verify it, since guessing from
 * grep'd raw hex codes alone had already caused one real mistake this
 * session):
 * - Color: `#E20714` primario (SOLO relleno: botón primario, ítem activo de
 *   nav, marca de celda editada -- nunca dentro de una tabla), `#B00510`
 *   hover/presionado, `#FDE8EA` selección/chip, `#1A1A18` tinta corporativa,
 *   `#5A5A5A`/`#8A8A8A` texto medio/suave, `#E4E4E7` borde, `#F4F4F5` fondo
 *   sutil, `#F7F7F8` fondo de página. Semántico (separado de marca, spec's
 *   own "regla de uso del rojo"): crítico `#C0392B`/fondo `#FDECEA`, alerta
 *   `#D97706`/fondo `#FEF3E2`, correcto `#15803D`/fondo `#ECFDF3`.
 * - Tipografía (Mulish, "sustituto web de Avenir Next"): título 32/700/1.2,
 *   pantalla 24/700/1.2, sección 20/600/1.3, cuerpo 16/400/1.4, interfaz
 *   14/500/1.4, tabla 13/400/1.2, rótulo 12/600/1.3. Cifras tabulares
 *   obligatorias en toda columna numérica (IBM Plex Mono).
 * - Espaciado (escala fija): 4 icono-a-texto, 8 entre controles, 12 padding
 *   de celda, 16 interior de tarjeta, 24 entre bloques, 32 entre secciones.
 * - Forma: radio 4px (chips/celdas), 8px (botones/tarjetas), 999px
 *   (píldoras). Una sola sombra: `0 1px 3px rgba(0,0,0,.08)`.
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
          --motored-brand-soft: #fde8ea;
          --motored-bg: #f7f7f8;
          --motored-surface: #ffffff;
          --motored-surface-alt: #f4f4f5;
          --motored-border: #e4e4e7;
          --motored-primary: var(--motored-brand);
          --motored-primary-dark: var(--motored-brand-dark);
          --motored-text: #1a1a18;
          --motored-text-muted: #5a5a5a;
          --motored-text-soft: #8a8a8a;
          --motored-danger: #c0392b;
          --motored-danger-bg: #fdecea;
          --motored-warning: #d97706;
          --motored-warning-bg: #fef3e2;
          --motored-success: #15803d;
          --motored-success-bg: #ecfdf3;
          --motored-radius-sm: 4px;
          --motored-radius-md: 8px;
          --motored-radius-pill: 999px;
          --motored-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
          --motored-space-1: 4px;
          --motored-space-2: 8px;
          --motored-space-3: 12px;
          --motored-space-4: 16px;
          --motored-space-5: 24px;
          --motored-space-6: 32px;
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

        /* Tipografía -- escala fija del sistema de diseño real (título/
        pantalla/sección/cuerpo/interfaz/tabla/rótulo), no valores libres. */
        .motored-theme .motored-h-titulo { font-size: 32px; font-weight: 700; line-height: 1.2; margin: 0; }
        .motored-theme .motored-h-pantalla { font-size: 24px; font-weight: 700; line-height: 1.2; margin: 0; }
        .motored-theme .motored-h-seccion { font-size: 20px; font-weight: 600; line-height: 1.3; margin: 0; }
        .motored-theme .motored-t-interfaz { font-size: 14px; font-weight: 500; line-height: 1.4; }
        .motored-theme .motored-t-rotulo { font-size: 12px; font-weight: 600; line-height: 1.3; text-transform: uppercase; letter-spacing: 0.04em; }

        /* Botones -- 4 variantes, cada una con su propia regla de uso
        (ver docstring del módulo): primario relleno, secundario outline
        neutro, terciario texto-link, destructivo outline por defecto
        (SOLO se rellena en :active, para no convertirse en un botón rojo
        permanente) -- y NUNCA destructivo dentro de una tabla (ver la
        clase motored-row-action para el caso de una fila). */
        .motored-theme .motored-btn {
          display: inline-flex; align-items: center; justify-content: center; gap: 6px;
          height: 36px; padding: 0 16px; border-radius: var(--motored-radius-md);
          font-family: inherit; font-size: 14px; font-weight: 600; cursor: pointer;
          border: 1px solid transparent; transition: background-color 0.15s, border-color 0.15s, color 0.15s;
        }
        .motored-theme .motored-btn:disabled { cursor: not-allowed; opacity: 0.5; }

        .motored-theme .motored-btn-primary { background: var(--motored-primary); color: #fff; }
        .motored-theme .motored-btn-primary:hover:not(:disabled) { background: var(--motored-primary-dark); }
        .motored-theme .motored-btn-primary:active:not(:disabled) { background: #7a1f16; }

        .motored-theme .motored-btn-secondary { background: var(--motored-surface); color: var(--motored-text); border-color: var(--motored-border); }
        .motored-theme .motored-btn-secondary:hover:not(:disabled) { background: var(--motored-surface-alt); }
        .motored-theme .motored-btn-secondary:active:not(:disabled) { background: var(--motored-border); }

        .motored-theme .motored-btn-tertiary { background: transparent; color: var(--motored-primary); padding: 0 8px; }
        .motored-theme .motored-btn-tertiary:hover:not(:disabled) { background: var(--motored-brand-soft); }

        .motored-theme .motored-btn-destructive { background: var(--motored-surface); color: var(--motored-danger); border-color: var(--motored-danger); }
        .motored-theme .motored-btn-destructive:hover:not(:disabled) { background: var(--motored-danger-bg); }
        .motored-theme .motored-btn-destructive:active:not(:disabled) { background: var(--motored-brand-dark); color: #fff; border-color: var(--motored-brand-dark); }

        /* Acción destructiva DENTRO de una fila de tabla: la regla del
        sistema real es explícita -- "Nunca un botón rojo dentro de una
        tabla". Se resuelve como un link de texto neutro, nunca rojo. */
        .motored-theme .motored-row-action {
          background: transparent; border: none; color: var(--motored-text-muted);
          font-family: inherit; font-size: 13px; font-weight: 600; cursor: pointer; padding: 0;
        }
        .motored-theme .motored-row-action:hover { color: var(--motored-text); text-decoration: underline; }

        /* Campos -- 36px, borde neutro, foco en rojo de marca. */
        .motored-theme input,
        .motored-theme select,
        .motored-theme textarea {
          font-family: inherit; font-size: 14px; color: var(--motored-text);
          background: var(--motored-surface); border: 1px solid var(--motored-border);
          border-radius: var(--motored-radius-md); height: 36px; padding: 0 12px;
        }
        .motored-theme textarea { height: auto; padding: 12px; }
        .motored-theme input:focus,
        .motored-theme select:focus,
        .motored-theme textarea:focus {
          outline: none; border-color: var(--motored-primary);
          box-shadow: 0 0 0 3px var(--motored-brand-soft);
        }

        /* Tooltip de ayuda -- convención para TODO campo cuyo nombre no sea
        obvio para alguien de negocio (p.ej. "SIC", "Días de seguridad").
        Ver componente InfoTooltip.js en cada pantalla; esta es solo la
        presentación compartida. */
        .motored-theme .motored-tooltip {
          position: relative; display: inline-flex; align-items: center;
          margin-left: 4px; color: var(--motored-text-soft); cursor: help;
        }
        .motored-theme .motored-tooltip-text {
          visibility: hidden; opacity: 0; position: absolute; bottom: 140%; left: 50%;
          transform: translateX(-50%); background: var(--motored-text); color: #fff;
          padding: 6px 10px; border-radius: var(--motored-radius-sm); font-size: 11px;
          font-weight: 500; line-height: 1.4; white-space: normal; width: max-content;
          max-width: 220px; text-align: left; transition: opacity 0.15s; z-index: 20;
        }
        .motored-theme .motored-tooltip:hover .motored-tooltip-text,
        .motored-theme .motored-tooltip:focus-visible .motored-tooltip-text {
          visibility: visible; opacity: 1;
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
