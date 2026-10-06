// Minimal shared HTML shell for the local test page.
import './globals.css';
import type { ReactNode } from 'react';
export const metadata = { title: 'CareLoop Test Upload' };
export default function Layout({ children }: { children: ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
