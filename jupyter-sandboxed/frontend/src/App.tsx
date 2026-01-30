import { useState, useEffect } from 'react'

interface Session {
  session_id: string
  jupyter_url: string
  status: string
  created_at: string
}

function App() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [isCreating, setIsCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchSessions = async () => {
    try {
      const response = await fetch('/api/sessions')
      const data = await response.json()
      setSessions(data.sessions)
    } catch (err) {
      console.error('Failed to fetch sessions:', err)
    }
  }

  useEffect(() => {
    fetchSessions()
    const interval = setInterval(fetchSessions, 5000)
    return () => clearInterval(interval)
  }, [])

  const createSession = async () => {
    setIsCreating(true)
    setError(null)
    try {
      const response = await fetch('/api/sessions', { method: 'POST' })
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
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Jupyter Sandbox</h1>
              <p className="text-gray-600 mt-1">Launch on-demand Jupyter notebooks</p>
            </div>
            <button
              onClick={createSession}
              disabled={isCreating}
              className={`px-6 py-3 rounded-lg font-medium text-white transition-colors ${
                isCreating
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-blue-600 hover:bg-blue-700'
              }`}
            >
              {isCreating ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
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
                    className="border border-gray-200 rounded-lg p-4 flex items-center justify-between"
                  >
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
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:underline font-medium"
                        >
                          {session.jupyter_url}
                        </a>
                      </div>
                      <div className="mt-1 text-sm text-gray-500">
                        Created: {formatTime(session.created_at)} · Status: {session.status}
                      </div>
                    </div>
                    <button
                      onClick={() => terminateSession(session.session_id)}
                      className="ml-4 px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                    >
                      Terminate
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="mt-8 pt-6 border-t border-gray-200 text-sm text-gray-500">
            Sessions automatically terminate after 1 hour of inactivity.
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
