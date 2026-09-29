'use client';
/**
 * frontend/components/motored/useDrawerMenu.js
 *
 * Open/closed state of the Motored off-canvas menu (odd/motored-responsive-
 * tablet, T1). The drawer closes on Escape and whenever the route changes.
 */
import { useCallback, useEffect, useState } from 'react';

export default function useDrawerMenu(pathname) {
  const [open, setOpen] = useState(false);
  const openMenu = useCallback(() => setOpen(true), []);
  const closeMenu = useCallback(() => setOpen(false), []);

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open]);

  return { open, openMenu, closeMenu };
}
