export const toast = {
  error:   (message) => _emit('error',   message),
  success: (message) => _emit('success', message),
  info:    (message) => _emit('info',    message),
};

function _emit(type, message) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent('app-toast', { detail: { type, message } }));
}
