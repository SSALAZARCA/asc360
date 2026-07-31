'use client';

import { useEffect, useState } from 'react';
import { authFetch } from '../lib/authFetch';

/**
 * EvidencePhoto — renders one damage-evidence photo from a service order's
 * reception (`ServiceOrderReception.damage_photos_urls[index]`).
 *
 * The stored `url` is built by `pdf_service.upload_file_to_minio` with a
 * hardcoded `http://localhost:9000/...` host, which only resolves on the
 * SERVER, never the browser — so it can never be rendered directly in
 * production. Instead, this component fetches the photo's bytes through
 * the authenticated proxy endpoint (`GET /orders/{orderId}/evidence-photos/
 * {index}`) and renders the resulting blob as an object URL, mirroring the
 * same pattern already used for the delivery-act download in
 * `distribuidor/entrega`.
 *
 * Fails soft: any fetch error or non-OK response renders nothing (matches
 * the existing `onError={e => e.target.style.display='none'}` fail-soft
 * behavior these thumbnails already had before this component existed).
 */
export default function EvidencePhoto({ orderId, index, alt }) {
  const [objectUrl, setObjectUrl] = useState(null);

  useEffect(() => {
    let cancelled = false;
    let localUrl = null;

    async function load() {
      try {
        const res = await authFetch(`/orders/${orderId}/evidence-photos/${index}`);
        if (!res.ok) return;
        const blob = await res.blob();
        if (cancelled) return;
        localUrl = URL.createObjectURL(blob);
        setObjectUrl(localUrl);
      } catch {
        // Fail soft: no photo rendered, rest of the page stays intact.
      }
    }

    load();

    return () => {
      cancelled = true;
      if (localUrl && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(localUrl);
    };
  }, [orderId, index]);

  if (!objectUrl) return null;

  return (
    <a href={objectUrl} target="_blank" rel="noreferrer" className="mphoto-thumb">
      <img src={objectUrl} alt={alt} />
    </a>
  );
}
