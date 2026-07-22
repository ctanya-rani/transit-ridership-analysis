'use client'

import { useEffect, useRef, useState } from 'react'

const MAX_UPLOAD_BYTES = 50 * 1024 * 1024

async function extractError(response: Response): Promise<string> {
  try {
    const data = await response.json()
    if (data?.detail) return String(data.detail)
  } catch {
    // response wasn't JSON — fall through to the generic message
  }
  return `${response.status} ${response.statusText}`
}

const UPLOAD_STAGES = [
  'Uploading feed…',
  'Validating & parsing GTFS…',
  'Simulating ridership…',
  'Rendering dashboard…',
]

export default function Home() {
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState<'demo' | 'upload' | null>(null)
  const [loadingStage, setLoadingStage] = useState('')
  const [error, setError] = useState('')
  const [dashboard, setDashboard] = useState<string | null>(null)
  const [dashboardLabel, setDashboardLabel] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const stageTimer = useRef<ReturnType<typeof setInterval> | null>(null)

  const apiUrl = process.env.NEXT_PUBLIC_API_URL

  const beginStagedMessages = () => {
    let i = 0
    setLoadingStage(UPLOAD_STAGES[0])
    stageTimer.current = setInterval(() => {
      i = Math.min(i + 1, UPLOAD_STAGES.length - 1)
      setLoadingStage(UPLOAD_STAGES[i])
    }, 2200)
  }

  const endStagedMessages = () => {
    if (stageTimer.current) clearInterval(stageTimer.current)
    stageTimer.current = null
    setLoadingStage('')
  }

  // Resize the dashboard iframe to fit its content, on load and on viewport
  // resize (the dashboard's own SVGs are percentage-width, so their
  // rendered height changes with the iframe's width).
  useEffect(() => {
    if (!dashboard) return
    const iframe = iframeRef.current
    if (!iframe) return

    const resize = () => {
      try {
        const doc = iframe.contentDocument
        if (doc) iframe.style.height = `${doc.documentElement.scrollHeight}px`
      } catch {
        // cross-origin or not yet loaded — ignore, next load/resize will retry
      }
    }

    iframe.addEventListener('load', resize)
    let resizeTimer: ReturnType<typeof setTimeout>
    const onWindowResize = () => {
      clearTimeout(resizeTimer)
      resizeTimer = setTimeout(resize, 150)
    }
    window.addEventListener('resize', onWindowResize)

    return () => {
      iframe.removeEventListener('load', resize)
      window.removeEventListener('resize', onWindowResize)
      clearTimeout(resizeTimer)
    }
  }, [dashboard])

  const loadDemo = async () => {
    setLoading('demo')
    setLoadingStage('Loading demo dataset…')
    setError('')
    try {
      const response = await fetch(`${apiUrl}/api/demo`)
      if (!response.ok) throw new Error(await extractError(response))
      setDashboard(await response.text())
      setDashboardLabel('Demo dataset')
    } catch (err) {
      setError(`Couldn't load the demo: ${err instanceof Error ? err.message : err}`)
    } finally {
      setLoading(null)
      setLoadingStage('')
    }
  }

  const validateAndSetFile = (f: File) => {
    setError('')
    if (!f.name.toLowerCase().endsWith('.zip')) {
      setFile(null)
      setError('Please choose a .zip file — GTFS feeds are distributed as zip archives.')
      return
    }
    if (f.size > MAX_UPLOAD_BYTES) {
      setFile(null)
      setError(`That file is ${(f.size / 1e6).toFixed(1)} MB — the limit is 50 MB.`)
      return
    }
    setFile(f)
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
    const dropped = e.dataTransfer.files
    if (dropped.length > 0) validateAndSetFile(dropped[0])
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) validateAndSetFile(e.target.files[0])
  }

  const uploadAndProcess = async () => {
    if (!file) return
    setLoading('upload')
    setError('')
    beginStagedMessages()

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await fetch(`${apiUrl}/api/upload`, {
        method: 'POST',
        body: formData,
      })
      if (!response.ok) throw new Error(await extractError(response))
      setDashboard(await response.text())
      setDashboardLabel(file.name)
    } catch (err) {
      setError(`Couldn't analyze that feed: ${err instanceof Error ? err.message : err}`)
    } finally {
      setLoading(null)
      endStagedMessages()
    }
  }

  const downloadHtml = () => {
    if (!dashboard) return
    const blob = new Blob([dashboard], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `transit-dashboard-${dashboardLabel.replace(/[^a-z0-9.-]+/gi, '_')}.html`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const reset = () => {
    setDashboard(null)
    setDashboardLabel('')
    setFile(null)
    setError('')
  }

  return (
    <main>
      {!dashboard ? (
        <>
          <h1>Transit Ridership Analytics</h1>
          <p className="subtitle">
            Ingest any GTFS feed and analyze ridership patterns — instantly, in your browser.
          </p>

          <div className="section">
            <button
              onClick={loadDemo}
              disabled={loading !== null}
              style={{ width: '100%' }}
            >
              {loading === 'demo' ? loadingStage || 'Loading…' : 'Load Demo Dataset'}
            </button>
            {loading === 'demo' && (
              <div className="progress"><div className="progress-bar" /></div>
            )}
          </div>

          <div className="section">
            <h2>Or upload your own GTFS feed</h2>
            <p style={{ color: 'var(--text-secondary)' }}>
              Drop a .zip file from Sound Transit, Amsterdam GVB, or any agency's GTFS feed.
            </p>
            <div
              className="upload-area"
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click() }}
            >
              <div style={{ fontSize: 24, marginBottom: 8 }}>📦</div>
              <p style={{ margin: 0, fontWeight: 500 }}>
                {file ? `Selected: ${file.name}` : 'Drag a GTFS .zip here or click to browse'}
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
                disabled={loading !== null}
                style={{ marginTop: 12, width: '100%' }}
              >
                {loading === 'upload' ? loadingStage : 'Analyze Feed'}
              </button>
            )}
            {loading === 'upload' && (
              <div className="progress"><div className="progress-bar" /></div>
            )}
          </div>

          {error && <div className="error">{error}</div>}

          <footer>
            Feeds are processed in memory and simulated ridership is clearly labeled —
            nothing is stored beyond a short-lived cache keyed to the file's contents.
          </footer>
        </>
      ) : (
        <>
          <div className="dashboard-toolbar">
            <button onClick={reset}>← Back</button>
            <button onClick={downloadHtml} className="btn-secondary">
              Download HTML
            </button>
          </div>
          <iframe
            ref={iframeRef}
            srcDoc={dashboard}
            title={`Transit dashboard — ${dashboardLabel}`}
            className="dashboard-frame"
            sandbox="allow-scripts allow-same-origin allow-downloads"
          />
        </>
      )}
    </main>
  )
}
