import '@testing-library/jest-dom';

// jsdom does not implement scrollIntoView; several pages (e.g. the tg chat
// mini-apps) call it on every message render, so stub it globally to avoid
// unrelated TypeErrors in unrelated component tests.
if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView() {};
}
