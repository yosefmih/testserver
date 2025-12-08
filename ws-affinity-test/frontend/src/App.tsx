import { useState, useRef, useCallback } from 'react'

interface Message {
  id: number
  type: string
  content: string
  hostname: string
  timestamp: Date
}

interface HttpResponse {
  hostname: string
  relayed_to: number
}

export default function App() {
  const [connected, setConnected] = useState(false)
  const [wsHostname, setWsHostname] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState('')
  const [httpResponse, setHttpResponse] = useState<HttpResponse | null>(null)
  const [sending, setSending] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const msgIdRef = useRef(0)

  const addMessage = useCallback((type: string, content: string, hostname: string) => {
    setMessages(prev => [...prev, {
      id: msgIdRef.current++,
      type,
      content,
      hostname,
      timestamp: new Date()
    }])
  }, [])

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws`

    addMessage('system', `Connecting to ${wsUrl}...`, '-')
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      setConnected(true)
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      setWsHostname(data.hostname)
      if (data.session_id) {
        setSessionId(data.session_id)
      }
      addMessage(data.type, data.message, data.hostname)
    }

    ws.onclose = () => {
      setConnected(false)
      addMessage('system', 'Connection closed', '-')
      wsRef.current = null
    }

    ws.onerror = () => {
      addMessage('error', 'WebSocket error', '-')
    }

    wsRef.current = ws
  }, [addMessage])

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
    }
  }, [])

  const sendMessage = useCallback(async () => {
    if (!inputValue.trim()) return

    setSending(true)
    setHttpResponse(null)

    try {
      const response = await fetch('/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: inputValue })
      })
      const data = await response.json()
      setHttpResponse(data)
      setInputValue('')
    } catch (error) {
      setHttpResponse({ hostname: 'ERROR', relayed_to: 0 })
    } finally {
      setSending(false)
    }
  }, [inputValue])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && e.metaKey) {
      sendMessage()
    }
  }

  const affinityMatch = httpResponse && wsHostname && httpResponse.hostname === wsHostname

  return (
    <div>
      <h1 style={{ marginBottom: 20, color: '#00d9ff' }}>
        WebSocket Session Affinity Test
      </h1>

      <div style={{
        background: '#16213e',
        padding: 15,
        borderRadius: 8,
        marginBottom: 20,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: 10
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 12,
            height: 12,
            borderRadius: '50%',
            background: connected ? '#2ed573' : '#ff4757'
          }} />
          <span>{connected ? 'Connected' : 'Disconnected'}</span>
        </div>

        <div style={{ display: 'flex', gap: 15, flexWrap: 'wrap' }}>
          <div>
            <span>Pod: </span>
            <span style={{
              background: '#0f3460',
              padding: '5px 12px',
              borderRadius: 4,
              fontFamily: 'monospace',
              color: '#00d9ff'
            }}>
              {wsHostname || '-'}
            </span>
          </div>
          <div>
            <span>Session: </span>
            <span style={{
              background: '#0f3460',
              padding: '5px 12px',
              borderRadius: 4,
              fontFamily: 'monospace',
              color: '#ffa502',
              fontSize: 11
            }}>
              {sessionId ? sessionId.slice(0, 8) + '...' : '-'}
            </span>
          </div>
        </div>

        <button
          onClick={connected ? disconnect : connect}
          style={{
            background: '#00d9ff',
            color: '#1a1a2e',
            border: 'none',
            padding: '10px 20px',
            borderRadius: 6,
            cursor: 'pointer',
            fontWeight: 'bold'
          }}
        >
          {connected ? 'Disconnect' : 'Connect'}
        </button>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
        gap: 20
      }}>
        <div style={{ background: '#16213e', borderRadius: 8, padding: 15 }}>
          <h2 style={{
            fontSize: 14,
            textTransform: 'uppercase',
            color: '#888',
            marginBottom: 10,
            letterSpacing: 1
          }}>
            WebSocket Messages
          </h2>
          <div style={{
            height: 300,
            overflowY: 'auto',
            background: '#0f0f1a',
            borderRadius: 6,
            padding: 10,
            fontFamily: 'monospace',
            fontSize: 13
          }}>
            {messages.map(msg => (
              <div key={msg.id} style={{
                padding: 8,
                marginBottom: 8,
                borderRadius: 4,
                background: '#1a1a2e',
                borderLeft: '3px solid #00d9ff'
              }}>
                <div style={{ color: '#888', fontSize: 11, marginBottom: 4 }}>
                  {msg.timestamp.toLocaleTimeString()} | {msg.type} | pod: {msg.hostname}
                </div>
                <div style={{ color: '#fff' }}>{msg.content}</div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ background: '#16213e', borderRadius: 8, padding: 15 }}>
          <h2 style={{
            fontSize: 14,
            textTransform: 'uppercase',
            color: '#888',
            marginBottom: 10,
            letterSpacing: 1
          }}>
            Send via HTTP
          </h2>

          <textarea
            value={inputValue}
            onChange={e => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message... (Cmd+Enter to send)"
            disabled={!connected}
            style={{
              width: '100%',
              height: 150,
              background: '#0f0f1a',
              border: '1px solid #333',
              borderRadius: 6,
              padding: 10,
              color: '#eee',
              fontFamily: 'inherit',
              resize: 'vertical',
              marginBottom: 10
            }}
          />

          <button
            onClick={sendMessage}
            disabled={!connected || sending}
            style={{
              width: '100%',
              background: connected ? '#00d9ff' : '#555',
              color: '#1a1a2e',
              border: 'none',
              padding: '10px 20px',
              borderRadius: 6,
              cursor: connected ? 'pointer' : 'not-allowed',
              fontWeight: 'bold',
              marginBottom: 10
            }}
          >
            {sending ? 'Sending...' : 'Send to HTTP Endpoint'}
          </button>

          <div style={{
            padding: 10,
            background: '#0f0f1a',
            borderRadius: 6,
            fontFamily: 'monospace',
            fontSize: 12,
            color: '#888'
          }}>
            {httpResponse ? (
              <>
                <div>HTTP Response from pod: <strong>{httpResponse.hostname}</strong></div>
                <div>WebSocket on pod: <strong>{wsHostname}</strong></div>
                <div>Relayed to: {httpResponse.relayed_to} connection(s)</div>
                <div style={{
                  marginTop: 8,
                  color: affinityMatch ? '#2ed573' : '#ff4757',
                  fontWeight: 'bold'
                }}>
                  {affinityMatch
                    ? '✓ Same pod - affinity working!'
                    : '✗ Different pod - affinity broken!'}
                </div>
              </>
            ) : (
              'HTTP response will appear here'
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
