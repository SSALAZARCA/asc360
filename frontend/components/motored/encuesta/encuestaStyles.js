// Stylesheet scoped under .enc-root. Tokens come from the offline design canvas
// "Encuesta Motored". Never put backticks inside the CSS comments below.
export const encuestaCss = `
.enc-root { min-height: 100vh; background: #F2F2F0; display: flex; justify-content: center;
  font-family: var(--enc-font), -apple-system, 'Segoe UI', sans-serif; font-weight: 500;
  font-variant-numeric: tabular-nums; color: #1A1A18; }
.enc-root *, .enc-root *::before, .enc-root *::after { box-sizing: border-box; border-radius: 0 !important; }
.enc-root button, .enc-root input, .enc-root textarea { font-family: inherit; }
.enc-root :focus-visible { outline: 3px solid #1D4E89; outline-offset: 2px; }
.enc-card { width: 100%; max-width: 480px; background: #FFFFFF; display: flex; flex-direction: column; min-height: 100vh; }
@media (min-width: 600px) {
  .enc-root { padding: 24px 0; }
  .enc-card { min-height: calc(100vh - 48px); border: 1px solid #E4E4E1; }
}
.enc-header { position: relative; overflow: hidden; background: #F2F2F0; padding: 10px 16px;
  display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.enc-header img { height: 26px; width: auto; display: block; position: relative; z-index: 1; }
.enc-label { font-size: 12px; line-height: 16px; font-weight: 700; letter-spacing: .08em; color: #595954; position: relative; z-index: 1; }
.enc-stripe { position: absolute; top: 0; bottom: 0; right: -18px; width: 26px; background: #E20714; transform: skewX(-14deg); }
.enc-progress { height: 4px; background: #E4E4E1; }
.enc-progress > div { height: 100%; background: #E20714; transition: width 200ms; }
.enc-offline { background: #1A1A18; padding: 14px 20px; color: #FFFFFF; }
.enc-offline strong { display: block; font-size: 17px; line-height: 24px; font-weight: 700; }
.enc-offline span { font-size: 15px; line-height: 23px; color: #E4E4E1; }
.enc-body { flex: 1; display: flex; flex-direction: column; padding: 14px 16px 24px; }
.enc-step { font-size: 12px; line-height: 16px; font-weight: 700; letter-spacing: .08em; color: #6E6E68; }
.enc-greeting { font-size: 17px; line-height: 27px; color: #3D3D3A; margin: 0 0 6px; }
.enc-question { font-size: 22px; line-height: 29px; font-weight: 700; color: #1A1A18; margin: 8px 0 0; display: block; }
.enc-title { font-size: 36px; line-height: 42px; font-weight: 700; margin: 14px 0 0; }
.enc-text { font-size: 17px; line-height: 27px; color: #3D3D3A; margin: 14px 0 0; }
.enc-hint { font-size: 15px; line-height: 23px; color: #595954; margin: 8px 0 0; }
.enc-error { font-size: 15px; line-height: 23px; color: #B01018; font-weight: 700; margin: 12px 0 0; }
.enc-input, .enc-textarea { width: 100%; border: 1px solid #C9C9C6; background: #FFFFFF; color: #1A1A18;
  font-size: 17px; line-height: 27px; padding: 12px; margin-top: 18px; }
.enc-input { min-height: 52px; }
.enc-textarea { resize: none; margin-top: 16px; }
.enc-counter { text-align: right; font-size: 12px; line-height: 16px; color: #6E6E68; margin-top: 6px; }
.enc-counter.is-warning { color: #7A5B00; font-weight: 700; }
.enc-options { display: flex; flex-direction: column; gap: 10px; margin-top: 22px; }
.enc-option { display: flex; align-items: baseline; gap: 12px; width: 100%; min-height: 56px; padding: 10px 14px;
  border: 1px solid #C9C9C6; background: #FFFFFF; color: #1A1A18; text-align: left; font-size: 17px; cursor: pointer; }
.enc-option strong { font-weight: 700; font-size: 20px; }
.enc-scale { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin-top: 22px; }
.enc-choice { min-height: 56px; border: 1px solid #C9C9C6; background: #FFFFFF; color: #3D3D3A;
  font-size: 20px; font-weight: 700; cursor: pointer; transition: background 150ms, border-color 150ms; }
.enc-choice[aria-checked="true"] { background: #E20714; border-color: #E20714; color: #FFFFFF; }
.enc-choice:active { background: #B01018; color: #FFFFFF; }
.enc-choice:disabled { cursor: default; }
.enc-ends { display: flex; justify-content: space-between; gap: 8px; margin-top: 8px; font-size: 12px; line-height: 16px;
  font-weight: 700; letter-spacing: .08em; color: #595954; }
.enc-word { min-height: 30px; margin-top: 14px; font-size: 20px; line-height: 26px; font-weight: 700; color: #1A1A18; }
.enc-yesno { display: flex; flex-direction: column; gap: 10px; margin-top: 22px; }
.enc-yesno .enc-choice { min-height: 64px; width: 100%; }
.enc-legend { font-size: 12px; line-height: 16px; letter-spacing: .08em; color: #595954; margin-top: 10px; display: flex; justify-content: space-between; }
.enc-cards { display: flex; flex-direction: column; gap: 10px; margin-top: 14px; }
.enc-card-row { border: 1px solid #E4E4E1; padding: 12px; background: #FFFFFF; }
.enc-card-row.is-done { border-color: #C9C9C6; background: #F8F8F7; }
.enc-card-row p { margin: 0 0 10px; font-size: 15px; line-height: 23px; color: #1A1A18; }
.enc-matrix { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; }
.enc-matrix .enc-choice { min-height: 48px; font-size: 17px; }
.enc-matrix .enc-choice.enc-na { grid-column: 1 / -1; min-height: 44px; border-style: dashed; border-color: #A3A39E;
  background: transparent; color: #595954; font-size: 12px; letter-spacing: .08em; }
.enc-matrix .enc-choice.enc-na[aria-checked="true"] { border-style: solid; background: #1A1A18; border-color: #1A1A18; color: #FFFFFF; }
.enc-footer { position: sticky; bottom: 0; margin-top: auto; background: #FFFFFF; border-top: 1px solid #E4E4E1; padding: 12px 16px; }
.enc-footer-row { display: flex; gap: 10px; align-items: stretch; }
.enc-helper { font-size: 12px; line-height: 16px; color: #595954; margin: 0 0 8px; }
.enc-back { flex: none; min-height: 52px; padding: 0 16px; background: transparent; border: 1px solid #C9C9C6; color: #3D3D3A;
  font-size: 12px; font-weight: 700; letter-spacing: .08em; cursor: pointer; }
.enc-cta { flex: 1; min-height: 52px; border: none; background: #E20714; color: #FFFFFF; font-size: 17px; font-weight: 700; cursor: pointer; }
.enc-cta:active:not(:disabled) { background: #B01018; }
.enc-cta:disabled { background: #A3A39E; cursor: default; }
.enc-retry { margin-top: 14px; min-height: 52px; padding: 0 20px; border: 1px solid #1A1A18; background: #FFFFFF; color: #1A1A18; font-size: 17px; font-weight: 700; cursor: pointer; }
.enc-closing { flex: 1; display: flex; flex-direction: column; }
.enc-closing.is-dark { background: #1A1A18; color: #FFFFFF; }
.enc-closing.is-dark .enc-text { color: #E4E4E1; }
.enc-closing-main { padding: 28px 20px 0; flex: 1; }
.enc-case { margin-top: 24px; border: 1px solid #E4E4E1; padding: 16px; }
.enc-case .enc-step { color: #E4E4E1; }
.enc-case-number { font-size: 36px; line-height: 42px; font-weight: 700; margin-top: 6px; overflow-wrap: anywhere; }
@media (max-width: 400px) { .enc-case-number { font-size: 28px; line-height: 34px; } }
.enc-case p { margin: 8px 0 0; font-size: 15px; line-height: 23px; color: #E4E4E1; }
.enc-band { position: relative; overflow: hidden; background: #1A1A18; height: 72px; margin-top: 28px; }
.enc-band::before { content: ''; position: absolute; top: 0; bottom: 0; left: -14px; width: 20px; background: #E20714; transform: skewX(-14deg); }
@media (prefers-reduced-motion: reduce) { .enc-root * { transition: none !important; } }
`;
