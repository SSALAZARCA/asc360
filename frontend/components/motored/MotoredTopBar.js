'use client';
/**
 * frontend/components/motored/MotoredTopBar.js
 *
 * Top bar with the menu button and logo. It is only visible below 1024px
 * (`.motored-topbar` in the theme CSS); on desktop the sidebar is always
 * on screen and this bar is hidden.
 */
import Image from 'next/image';
import { Menu } from 'lucide-react';

export default function MotoredTopBar({ onOpenMenu }) {
  return (
    <header className="motored-topbar">
      <button type="button" className="motored-topbar-btn" aria-label="Abrir menú" onClick={onOpenMenu}>
        <Menu size={22} />
      </button>
      <Image src="/motored-logo.png" alt="Motored" width={104} height={34} />
    </header>
  );
}
