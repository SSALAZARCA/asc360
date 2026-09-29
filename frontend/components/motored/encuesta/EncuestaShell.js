import { COPY } from './copy';
import { encuestaCss } from './encuestaStyles';

/**
 * Presentational frame: header, progress bar, offline banner and sticky footer.
 * `progress` (0..1) is only passed on question screens.
 * `footer` = { onBack, cta: { label, disabled, onClick }, helper }.
 */
export default function EncuestaShell({ fontClassName = '', offline, progress, footer, children }) {
  return (
    <div className={`enc-root ${fontClassName}`}>
      <style>{encuestaCss}</style>
      <div className="enc-card">
        <header className="enc-header">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/motored-logo.png" alt="Motored" />
          <span className="enc-label">{COPY.label}</span>
          <div className="enc-stripe" aria-hidden="true" />
        </header>
        {progress != null && (
          <div className="enc-progress" aria-hidden="true">
            <div style={{ width: `${Math.round(progress * 100)}%` }} />
          </div>
        )}
        {offline && (
          <div className="enc-offline" role="status">
            <strong>{COPY.offline}</strong>
            <span>{COPY.offlineHint}</span>
          </div>
        )}
        {children}
        {footer && (
          <footer className="enc-footer">
            {footer.helper && <p className="enc-helper">{footer.helper}</p>}
            <div className="enc-footer-row">
              {footer.onBack && (
                <button type="button" className="enc-back" onClick={footer.onBack}>
                  Atrás
                </button>
              )}
              {footer.cta && (
                <button type="button" className="enc-cta" disabled={footer.cta.disabled} onClick={footer.cta.onClick}>
                  {footer.cta.label}
                </button>
              )}
            </div>
          </footer>
        )}
      </div>
    </div>
  );
}
