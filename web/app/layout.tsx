// Minimal shared HTML shell for the AfterWard pages.
import './globals.css';
import type { ReactNode } from 'react';
export const metadata = { title: 'AfterWard' };
export default function Layout({ children }: { children: ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
