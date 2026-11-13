import type { Metadata } from 'next';
import Link from 'next/link';
import './globals.css';

export const metadata: Metadata = {
  title: 'Potato Marketplace · Development',
  description: 'Sandbox-only local marketplace MVP',
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="ru"><body>
    <header><strong>Potato Marketplace</strong><nav aria-label="Разделы">
      <Link href="/">Витрина</Link><Link href="/seller">Продавец</Link><Link href="/moderation">Модерация</Link>
    </nav><span>Local sandbox</span></header>
    <main>{children}</main>
  </body></html>;
}
