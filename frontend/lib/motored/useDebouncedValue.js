'use client';
/**
 * frontend/lib/motored/useDebouncedValue.js
 *
 * Returns `value` only after it stopped changing for `delayMs`. Used by the
 * Referencias search box and the sustituta type-ahead so typing does not
 * fire one request per keystroke.
 */
import { useEffect, useState } from 'react';

export default function useDebouncedValue(value, delayMs = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}
