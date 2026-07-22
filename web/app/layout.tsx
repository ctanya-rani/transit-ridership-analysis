import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Transit Ridership Analytics',
  description:
    'Upload any GTFS feed — or explore the bundled Sound Transit-modeled ' +
    'demo — and get an interactive ridership dashboard.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
