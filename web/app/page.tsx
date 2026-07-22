'use client'

import { useState, useRef } from 'react'

export default function Home() {
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [dashboard, setDashboard] = useState<string | null>(null)
  const [mode, setMode] = useState<'demo' | 'upload'>('demo')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const apiUrl = process.env.NEXT_PUBLIC_API_URL

  const loadDemo = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${apiUrl}/api/demo`)
      if (!response.ok) throw new Error(`API error: ${response.status}`)
      const html = await response.text()
      setDashboard(html)
    } catch (err) {
      setError(`Failed to load demo: ${err}`)
    } finally {
      setLoading(false)
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.currentTarget.classList.add('drag')
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.currentTarget.classList.remove('drag')
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.currentTarget.classList.remove('drag')
    const files = e.dataTransfer.files
    if (files.length > 0) {
      setFile(files[0])
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) {
      setFile(e.target.files[0])
    }
  }

  const uploadAndProcess = async () => {
    if (!file) return
    setLoading(true)
    setError('')

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await fetch(`${apiUrl}/api/upload`, {
        method: 'POST',
        body: formData,
      })
      if (!response.ok) throw new Error(`API error: ${response.status}`)
      const html = await response.text()
      setDashboard(html)
    } catch (err) {
      setError(`Failed to process feed: ${err}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main>
      <h1>Transit Ridership Analytics</h1>
      <p className="subtitle">
        Ingest any GTFS feed and analyze ridership patterns
      </p>

      {!dashboard ? (
        <>
          <div className="info-grid">
            <button
              onClick={() => { setMode('demo'); loadDemo() }}
              style={{
                background: mode === 'demo' ? '#2a78d6' : '#c3c2b7',
                gridColumn: '1 / -1',
              }}
            >
              {loading && mode === 'demo' ? 'Loading demo…' : 'Load Demo Dataset'}
            </button>
          </div>

          <div className="section">
            <h2>Or upload your own GTFS feed</h2>
            <p style={{ color: 'var(--text-secondary)' }}>
              Paste a .zip file from Sound Transit, Amsterdam GVB, or any GTFS feed.
            </p>
            <div
              className="upload-area"
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <div style={{ fontSize: 24, marginBottom: 8 }}>📦</div>
              <p style={{ margin: 0, fontWeight: 500 }}>
                {file
                  ? `Selected: ${file.name}`
                  : 'Drag a GTFS .zip here or click to browse'}
              </p>
              <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--text-secondary)' }}>
                Max 50 MB
              </p>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip"
              onChange={handleFileSelect}
            />
            {file && (
              <button
                onClick={uploadAndProcess}
                disabled={loading}
                style={{ marginTop: 12, width: '100%' }}
              >
                {loading ? 'Processing feed…' : 'Analyze Feed'}
              </button>
            )}
            {loading && <div className="progress"><div className="progress-bar" /></div>}
          </div>

          {error && <div className="error">{error}</div>}
        </>
      ) : (
        <>
          <button onClick={() => setDashboard(null)} style={{ marginBottom: 12 }}>
            ← Back
          </button>
          <div
            className="dashboard-container"
            dangerouslySetInnerHTML={{ __html: dashboard }}
          />
        </>
      )}
    </main>
  )
}
