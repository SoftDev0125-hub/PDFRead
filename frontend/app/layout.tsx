import type { Metadata } from 'next'
import '../src/index.css'

export const metadata: Metadata = {
  title: 'Lab Report Biomarker Extractor',
  description: 'Upload PDFs/images and extract biomarkers.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}

