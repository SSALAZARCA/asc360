'use client';
/**
 * frontend/lib/motored/useAdminGate.js
 *
 * sdd/motored-ventas-perdidas-panel, Phase 5 (design D6): shared extraction
 * of the ADMIN-gate hook that already lived inline in
 * `app/motored/usuarios/page.js` -- the same logic (same sessionStorage key,
 * same JSON-parse-failure handling; the only difference is that this hook
 * sends SERVICIO_CLIENTE to its survey page instead of /motored/maestros),
 * just moved here so other ADMIN-only pages (starting with this
 * change's own `ventas-perdidas/page.js`, Phase 7) can reuse it without
 * copy-pasting.
 *
 * `usuarios/page.js` itself keeps its own local copy and is DELIBERATELY NOT
 * refactored to import this hook in this phase (design D6's own accepted
 * tradeoff: avoids an unrelated diff in an unrelated file under `gga`'s
 * whole-file review -- this is intentional duplication, not an oversight).
 */
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { MOTORED_USER_KEY } from './motoredFetch';
import { homePathFor } from './session';

export default function useAdminGate() {
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);
  const [ownUserId, setOwnUserId] = useState(null);

  useEffect(() => {
    const stored = sessionStorage.getItem(MOTORED_USER_KEY);
    let parsed = null;
    try {
      parsed = stored ? JSON.parse(stored) : null;
    } catch {
      parsed = null;
    }
    if (parsed?.role !== 'ADMIN') {
      router.push(homePathFor(parsed?.role));
      return;
    }
    setOwnUserId(parsed.id ?? null);
    setAllowed(true);
  }, [router]);

  return { allowed, ownUserId };
}
