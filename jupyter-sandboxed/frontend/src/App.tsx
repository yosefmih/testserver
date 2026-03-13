import { useState, useEffect, useRef } from 'react'

interface Session {
  session_id: string
  jupyter_url: string
  status: string
  created_at: string
  iam_role_arn?: string
}

function App() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [isCreating, setIsCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [iamRoleArn, setIamRoleArn] = useState('')
  const [domain, setDomain] = useState('')
  const [expandedLogs, setExpandedLogs] = useState<Record<string, string[]>>({})
  const logRefs = useRef<Record<string, HTMLPreElement | null>>({})

  const fetchSessions = async () => {
    try {
      const response = await fetch('/api/sessions')
      const data = await response.json()
      setSessions(data.sessions)
    } catch (err) {
      console.error('Failed to fetch sessions:', err)
    }
  }

  const fetchLogs = async (sessionId: string) => {
    try {
      const response = await fetch(`/api/sessions/${sessionId}/logs`)
      const data = await response.json()
      setExpandedLogs((prev) => ({ ...prev, [sessionId]: data.logs }))
    } catch (err) {
      console.error('Failed to fetch logs:', err)
    }
  }

  useEffect(() => {
    fetchSessions()
    const interval = setInterval(fetchSessions, 5000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const activeLogSessions = Object.keys(expandedLogs)
    if (activeLogSessions.length === 0) return

    const interval = setInterval(() => {
      activeLogSessions.forEach((id) => fetchLogs(id))
    }, 3000)
    return () => clearInterval(interval)
  }, [Object.keys(expandedLogs).join(',')])

  useEffect(() => {
    Object.entries(logRefs.current).forEach(([id, el]) => {
      if (el && expandedLogs[id]) {
        el.scrollTop = el.scrollHeight
      }
    })
  }, [expandedLogs])

  const toggleLogs = (sessionId: string) => {
    if (expandedLogs[sessionId]) {
      setExpandedLogs((prev) => {
        const next = { ...prev }
        delete next[sessionId]
        return next
      })
    } else {
      fetchLogs(sessionId)
    }
  }

  const createSession = async () => {
    setIsCreating(true)
    setError(null)
    try {
      const body: Record<string, string> = {}
      if (iamRoleArn.trim()) {
        body.iam_role_arn = iamRoleArn.trim()
      }
      if (domain.trim()) {
        body.domain = domain.trim()
      }
      const response = await fetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Failed to create session')
      }
      await fetchSessions()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create session')
    } finally {
      setIsCreating(false)
    }
  }

  const terminateSession = async (sessionId: string) => {
    try {
      await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' })
      setExpandedLogs((prev) => {
        const next = { ...prev }
        delete next[sessionId]
        return next
      })
      await fetchSessions()
    } catch (err) {
      console.error('Failed to terminate session:', err)
    }
  }

  const formatTime = (isoString: string) => {
    return new Date(isoString).toLocaleString()
  }

  return (
    <div className="min-h-screen bg-gray-100">
      <div className="max-w-4xl mx-auto py-12 px-4">
        <div className="bg-white rounded-lg shadow-lg p-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-gray-900">Jupyter Sandbox</h1>
            <p className="text-gray-600 mt-1">Launch on-demand Jupyter notebooks with optional AWS access</p>
          </div>

          <div className="mb-6 p-4 bg-gray-50 rounded-lg border border-gray-200">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Domain (optional)
            </label>
            <input
              type="text"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              placeholder="my-notebook.example.com"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            <p className="mt-1 text-xs text-gray-500">
              Domain to access this Jupyter instance. A TLS certificate will be provisioned automatically.
            </p>

            <label className="block text-sm font-medium text-gray-700 mb-2 mt-4">
              IAM Role ARN (optional)
            </label>
            <input
              type="text"
              value={iamRoleArn}
              onChange={(e) => setIamRoleArn(e.target.value)}
              placeholder="arn:aws:iam::123456789012:role/my-role"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            <p className="mt-1 text-xs text-gray-500">
              If set, the notebook will have AWS credentials for this role via Pod Identity.
              Use boto3 directly in your notebook to access AWS services.
            </p>
            <button
              onClick={createSession}
              disabled={isCreating}
              className={`mt-3 px-6 py-2 rounded-lg font-medium text-white transition-colors ${
                isCreating
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-blue-600 hover:bg-blue-700'
              }`}
            >
              {isCreating ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Creating...
                </span>
              ) : (
                'Launch Jupyter'
              )}
            </button>
          </div>

          {error && (
            <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
              {error}
            </div>
          )}

          <div>
            <h2 className="text-xl font-semibold text-gray-800 mb-4">Active Sessions</h2>
            {sessions.length === 0 ? (
              <div className="text-center py-12 text-gray-500">
                <p>No active sessions</p>
                <p className="text-sm mt-1">Click "Launch Jupyter" to create one</p>
              </div>
            ) : (
              <div className="space-y-4">
                {sessions.map((session) => (
                  <div
                    key={session.session_id}
                    className="border border-gray-200 rounded-lg overflow-hidden"
                  >
                    <div className="p-4 flex items-center justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-3">
                          <span
                            className={`inline-block w-2 h-2 rounded-full ${
                              session.status === 'running'
                                ? 'bg-green-500'
                                : session.status === 'creating'
                                ? 'bg-yellow-500 animate-pulse'
                                : 'bg-gray-400'
                            }`}
                          />
                          <a
                            href={session.jupyter_url}
                            target="_blank"
                            className="text-blue-600 hover:underline font-medium"
                          >
                            Open Jupyter Lab
                          </a>
                        </div>
                        <div className="mt-1 text-sm text-gray-500">
                          Created: {formatTime(session.created_at)} · Status: {session.status}
                          {session.iam_role_arn && (
                            <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800">
                              AWS: {session.iam_role_arn.split('/').pop()}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => toggleLogs(session.session_id)}
                          className="px-3 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors text-sm"
                        >
                          {expandedLogs[session.session_id] ? 'Hide Logs' : 'Logs'}
                        </button>
                        <button
                          onClick={() => terminateSession(session.session_id)}
                          className="px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                        >
                          Terminate
                        </button>
                      </div>
                    </div>
                    {expandedLogs[session.session_id] && (
                      <div className="border-t border-gray-200 bg-gray-900">
                        <pre
                          ref={(el) => { logRefs.current[session.session_id] = el }}
                          className="p-4 text-xs text-green-400 font-mono overflow-auto max-h-80 whitespace-pre-wrap"
                        >
                          {expandedLogs[session.session_id].length > 0
                            ? expandedLogs[session.session_id].join('\n')
                            : 'No logs yet...'}
                        </pre>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="mt-8 pt-6 border-t border-gray-200 text-sm text-gray-500">
            Sessions automatically terminate after 1 hour.
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
