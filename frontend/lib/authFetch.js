/**
 * authFetch.js
 * Helper centralizado para hacer peticiones a la API con el JWT inyectado
 * automáticamente desde localStorage.
 * 
 * Uso: import { authFetch } from '@/lib/authFetch'
 *      const res = await authFetch('/orders/analytics/kpis')
 */

const API = () => process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

export async function authFetch(path, options = {}) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('um_token') : null;

  // Si el body es FormData el browser debe setear el Content-Type con el boundary,
  // no lo forzamos nosotros o el multipart queda malformado y FastAPI devuelve 422.
  const isFormData = options.body instanceof FormData;

  const headers = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  const url = path.startsWith('http') ? path : `${API()}${path}`;

  const response = await fetch(url, {
    ...options,
    headers,
  });

  // Si el servidor responde con 401 (token vencido o inválido), limpiar sesión
  if (response.status === 401) {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('um_token');
      localStorage.removeItem('um_user');
      window.dispatchEvent(new Event('storage'));
    }
  }

  return response;
}

/**
 * authFetchJson - Igual que authFetch pero ya parsea el JSON
 */
export async function authFetchJson(path, options = {}) {
  const res = await authFetch(path, options);
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorBody.detail || `HTTP ${res.status}`);
  }
  return res.json();
}
