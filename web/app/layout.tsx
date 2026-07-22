import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Transit Ridership Analytics',
  description: 'Analyze GTFS ridership data',
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
