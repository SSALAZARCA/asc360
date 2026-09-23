'use client';
/**
 * frontend/app/motored/cargas/page.js
 *
 * Retired route (sdd/motored-cargas-tipo-declarado; design D5). The
 * standalone "Cargas" screen was consolidated into `/motored/maestros`
 * (6 new movement tabs, `MovimientoTab.js`) -- the sidebar entry that
 * pointed here is gone (`MotoredSidebar.js`), but a bookmark/deep link to
 * this URL must NOT 404 silently (spec "A bookmark / deep link to
 * `/motored/cargas` must not 404 silently"). This page now does nothing
 * but redirect, client-side, to the consolidated screen.
 *
 * `app/motored/cargas/[id]/page.js` (the generic detail view, `tipo`-
 * agnostic) is explicitly OUT of this change's scope and stays untouched.
 */
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function CargasPageRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/motored/maestros');
  }, [router]);

  return null;
}
