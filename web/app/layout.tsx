import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Transit Ridership Analytics',
  description:
    'Upload any GTFS feed — or explore the bundled Sound Transit-modeled ' +
    'demo — and get an interactive ridership dashboard.',
  openGraph: {
    title: 'Transit Ridership Analytics',
    description: 'Analyze ridership patterns from any GTFS feed. Instant, interactive dashboards.',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Transit Ridership Analytics',
    description: 'Analyze ridership patterns from any GTFS feed.',
  },
  keywords: ['GTFS', 'transit', 'ridership', 'analytics', 'dashboard', 'public transport'],
  robots: 'index, follow',
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
