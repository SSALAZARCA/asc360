'use client';
import { authFetch } from './authFetch';
import { getApiUrl } from './api';

const BASE = () => `${getApiUrl()}/remisiones`;

/**
 * useRemisiones — API helpers for the Remisiones de Inventario module.
 *
 * All functions return the raw Response so callers can check `.ok` and parse
 * the body themselves, matching the authFetch pattern used project-wide.
 */
export function useRemisiones() {
  /**
   * List remisiones with optional filters.
   * @param {Object} filters - { type, status, reference_lot_id, date_from, date_to, page, page_size }
   */
  async function getRemisiones(filters = {}) {
    const params = new URLSearchParams();
    if (filters.type)             params.append('type', filters.type);
    if (filters.status)           params.append('status', filters.status);
    if (filters.reference_lot_id) params.append('reference_lot_id', filters.reference_lot_id);
    if (filters.date_from)        params.append('date_from', filters.date_from);
    if (filters.date_to)          params.append('date_to', filters.date_to);
    if (filters.page)             params.append('page', filters.page);
    if (filters.page_size)        params.append('page_size', filters.page_size);
    return authFetch(`${BASE()}/?${params}`);
  }

  /**
   * Get single remision detail (header + items + movements).
   * @param {string} id - UUID
   */
  async function getRemision(id) {
    return authFetch(`${BASE()}/${id}`);
  }

  /**
   * Create a new BORRADOR remision.
   * @param {Object} data - RemisionCreate payload
   */
  async function createRemision(data) {
    return authFetch(`${BASE()}/`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  /**
   * Update header fields of a BORRADOR remision (notes, reference_lot_id).
   * @param {string} id
   * @param {Object} data
   */
  async function updateRemision(id, data) {
    return authFetch(`${BASE()}/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  /**
   * Add an item to a BORRADOR remision.
   * @param {string} remisionId
   * @param {Object} itemData - { spare_part_item_id, qty_dispatched }
   */
  async function addItem(remisionId, itemData) {
    return authFetch(`${BASE()}/${remisionId}/items`, {
      method: 'POST',
      body: JSON.stringify(itemData),
    });
  }

  /**
   * Update qty of an existing item in a BORRADOR remision.
   * @param {string} remisionId
   * @param {string} itemId
   * @param {Object} data - { qty_dispatched }
   */
  async function updateItem(remisionId, itemId, data) {
    return authFetch(`${BASE()}/${remisionId}/items/${itemId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  /**
   * Remove an item from a BORRADOR remision.
   * @param {string} remisionId
   * @param {string} itemId
   */
  async function removeItem(remisionId, itemId) {
    return authFetch(`${BASE()}/${remisionId}/items/${itemId}`, {
      method: 'DELETE',
    });
  }

  /**
   * Dispatch a BORRADOR remision (BORRADOR → DESPACHADO).
   * @param {string} id
   */
  async function dispatchRemision(id) {
    return authFetch(`${BASE()}/${id}/despachar`, { method: 'POST' });
  }

  /**
   * Cancel a DESPACHADO remision (DESPACHADO → ANULADO).
   * @param {string} id
   * @param {string} reason - cancellation reason (required, min 5 chars)
   */
  async function cancelRemision(id, reason) {
    return authFetch(`${BASE()}/${id}/anular`, {
      method: 'POST',
      body: JSON.stringify({ cancellation_reason: reason }),
    });
  }

  async function deleteRemision(id) {
    return authFetch(`${BASE()}/${id}`, { method: 'DELETE' });
  }

  /**
   * Get available spare part items (qty_available > 0) for the item selector.
   * @param {Object} filters - { lot_id, part_number }
   */
  async function getAvailability(filters = {}) {
    const params = new URLSearchParams();
    if (filters.lot_id)     params.append('lot_id', filters.lot_id);
    if (filters.part_number) params.append('part_number', filters.part_number);
    return authFetch(`${BASE()}/availability?${params}`);
  }

  return {
    getRemisiones,
    getRemision,
    createRemision,
    updateRemision,
    addItem,
    updateItem,
    removeItem,
    dispatchRemision,
    cancelRemision,
    deleteRemision,
    getAvailability,
  };
}
