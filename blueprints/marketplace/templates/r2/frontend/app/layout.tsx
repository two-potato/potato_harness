import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Potato Marketplace · Development',
  description: 'Sandbox-only marketplace scaffold',
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return (
    <html lang="ru">
      <body><header><strong>Potato Marketplace</strong><span>Sandbox development</span></header><main>{children}</main></body>
    </html>
  );
}
