import { useState, useRef, useCallback, useEffect } from 'react'

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

  // Voice state
  const [voiceConnected, setVoiceConnected] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const [textToSpeak, setTextToSpeak] = useState('Hello, I am a robot. Testing graceful shutdown of voice calls.')
  const [shutdownWarning, setShutdownWarning] = useState<string | null>(null)
  const [audioProgress, setAudioProgress] = useState<{ chunks: number; total: number } | null>(null)
  const [narrateResponse, setNarrateResponse] = useState<{ status: string; hostname: string; error?: string } | null>(null)
  const [narrating, setNarrating] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const voiceWsRef = useRef<WebSocket | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const audioBuffersRef = useRef<ArrayBuffer[]>([])
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

  // Main WebSocket connection
  const connect = useCallback(() => {
    let clientSessionId = document.cookie.split('; ').find(c => c.startsWith('SESSION_ID='))?.split('=')[1]
    if (!clientSessionId) {
      clientSessionId = crypto.randomUUID()
      document.cookie = `SESSION_ID=${clientSessionId}; path=/; max-age=172800`
    }
    setSessionId(clientSessionId)

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws`

    addMessage('system', `Connecting with SESSION_ID=${clientSessionId.slice(0, 8)}...`, '-')
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => setConnected(true)

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      setWsHostname(data.hostname)
      if (data.session_id) setSessionId(data.session_id)
      if (data.type === 'shutdown_warning') {
        setShutdownWarning(data.message)
        addMessage('warning', `⚠️ ${data.message}`, data.hostname)
      } else {
        addMessage(data.type, data.message, data.hostname)
      }
    }

    ws.onclose = (event) => {
      setConnected(false)
      setShutdownWarning(null)
      addMessage('system', event.code === 1012 ? 'Server restarting - reconnect to continue' : 'Connection closed', '-')
      wsRef.current = null
    }

    ws.onerror = () => addMessage('error', 'WebSocket error', '-')
    wsRef.current = ws
  }, [addMessage])

  const disconnect = useCallback(() => {
    wsRef.current?.close()
    voiceWsRef.current?.close()
  }, [])

  // Voice WebSocket for robotic TTS
  const connectVoice = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const voiceUrl = `${protocol}//${window.location.host}/voice`

    addMessage('voice', 'Connecting to voice service...', '-')
    const ws = new WebSocket(voiceUrl)
    voiceWsRef.current = ws

    // Initialize audio context
    if (!audioContextRef.current) {
      audioContextRef.current = new AudioContext()
    }

    ws.onopen = () => {
      setVoiceConnected(true)
      addMessage('voice', 'Voice service connected', wsHostname || '-')
    }

    ws.onmessage = async (event) => {
      if (event.data instanceof Blob) {
        // Binary audio data
        const arrayBuffer = await event.data.arrayBuffer()
        audioBuffersRef.current.push(arrayBuffer)
        setAudioProgress(prev => prev ? { ...prev, chunks: prev.chunks + 1 } : { chunks: 1, total: 0 })
      } else {
        // JSON message
        const data = JSON.parse(event.data)
        if (data.type === 'call_started') {
          addMessage('voice', data.message, data.hostname)
        } else if (data.type === 'shutdown_warning') {
          setShutdownWarning(data.message)
          addMessage('warning', `⚠️ VOICE: ${data.message}`, data.hostname)
        } else if (data.type === 'interrupted') {
          setSpeaking(false)
          setAudioProgress({ chunks: data.chunks_sent, total: data.total_chunks })
          addMessage('warning', `🔇 ${data.message} (${data.chunks_sent}/${data.total_chunks} chunks)`, data.hostname)
          playCollectedAudio() // Play what we got before interruption
        } else if (data.type === 'speech_complete') {
          setSpeaking(false)
          addMessage('voice', `✓ ${data.message}`, data.hostname)
          playCollectedAudio()
        } else if (data.type === 'pong') {
          addMessage('voice', `Ping: ${data.call_duration_s}s, shutdown=${data.shutdown_pending}`, data.hostname)
        }
      }
    }

    ws.onclose = (event) => {
      setVoiceConnected(false)
      setSpeaking(false)
      addMessage('voice', event.code === 1012 ? 'Voice call ended - server restarting' : 'Voice disconnected', '-')
      voiceWsRef.current = null
    }

    ws.onerror = () => addMessage('error', 'Voice connection error', '-')
  }, [addMessage, wsHostname])

  const playCollectedAudio = useCallback(async () => {
    if (!audioContextRef.current || audioBuffersRef.current.length === 0) return

    try {
      // Combine all audio buffers
      const combined = new Blob(audioBuffersRef.current, { type: 'audio/wav' })
      const arrayBuffer = await combined.arrayBuffer()

      // Decode and play
      const audioBuffer = await audioContextRef.current.decodeAudioData(arrayBuffer)
      const source = audioContextRef.current.createBufferSource()
      source.buffer = audioBuffer
      source.connect(audioContextRef.current.destination)
      source.start()

      addMessage('voice', `🔊 Playing audio (${audioBuffersRef.current.length} chunks)`, '-')
    } catch (e) {
      addMessage('error', `Failed to play audio: ${e}`, '-')
    }

    // Clear buffers for next speech
    audioBuffersRef.current = []
    setAudioProgress(null)
  }, [addMessage])

  const speak = useCallback(() => {
    if (!voiceWsRef.current || voiceWsRef.current.readyState !== WebSocket.OPEN) {
      addMessage('error', 'Voice not connected', '-')
      return
    }

    audioBuffersRef.current = [] // Clear previous audio
    setSpeaking(true)
    setAudioProgress({ chunks: 0, total: 0 })

    voiceWsRef.current.send(JSON.stringify({
      action: 'speak',
      text: textToSpeak
    }))

    addMessage('voice', `🎤 Speaking: "${textToSpeak.slice(0, 40)}..."`, wsHostname || '-')
  }, [textToSpeak, wsHostname, addMessage])

  const disconnectVoice = useCallback(() => {
    voiceWsRef.current?.close()
  }, [])

  // HTTP narrate - tests session affinity for voice!
  const narrateViaHttp = useCallback(async () => {
    if (!voiceConnected) {
      addMessage('error', 'Voice not connected', '-')
      return
    }

    setNarrating(true)
    setNarrateResponse(null)
    audioBuffersRef.current = []
    setAudioProgress({ chunks: 0, total: 0 })

    addMessage('voice', `📡 Sending narrate request via HTTP...`, '-')

    try {
      const response = await fetch('/narrate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: textToSpeak })
      })
      const data = await response.json()
      setNarrateResponse(data)

      if (data.status === 'ok') {
        addMessage('voice', `✓ HTTP narrate: ${data.chunks_sent} chunks from pod ${data.hostname}`, data.hostname)
      } else {
        addMessage('error', `HTTP narrate failed: ${data.error}`, data.hostname)
        if (data.hint) {
          addMessage('warning', `💡 ${data.hint}`, '-')
        }
      }
    } catch (e) {
      setNarrateResponse({ status: 'error', hostname: 'ERROR', error: String(e) })
      addMessage('error', `HTTP narrate error: ${e}`, '-')
    } finally {
      setNarrating(false)
    }
  }, [voiceConnected, textToSpeak, addMessage])

  // HTTP affinity test
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
    } catch {
      setHttpResponse({ hostname: 'ERROR', relayed_to: 0 })
    } finally {
      setSending(false)
    }
  }, [inputValue])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && e.metaKey) sendMessage()
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      audioContextRef.current?.close()
    }
  }, [])

  const affinityMatch = httpResponse && wsHostname && httpResponse.hostname === wsHostname

  return (
    <div>
      <h1 style={{ marginBottom: 20, color: '#00d9ff' }}>
        WebSocket Affinity + Robotic Voice Test
      </h1>

      {shutdownWarning && (
        <div style={{
          background: '#ff4757',
          color: 'white',
          padding: 15,
          borderRadius: 8,
          marginBottom: 20,
          fontWeight: 'bold'
        }}>
          ⚠️ {shutdownWarning}
        </div>
      )}

      {/* Connection Status Bar */}
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 15 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 12, height: 12, borderRadius: '50%', background: connected ? '#2ed573' : '#ff4757' }} />
            <span>WS: {connected ? 'Connected' : 'Disconnected'}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 12, height: 12, borderRadius: '50%', background: voiceConnected ? '#2ed573' : '#ff4757' }} />
            <span>Voice: {voiceConnected ? 'Connected' : 'Disconnected'}</span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 15 }}>
          <div>
            <span>Pod: </span>
            <span style={{ background: '#0f3460', padding: '5px 12px', borderRadius: 4, fontFamily: 'monospace', color: '#00d9ff' }}>
              {wsHostname || '-'}
            </span>
          </div>
          <div>
            <span>Session: </span>
            <span style={{ background: '#0f3460', padding: '5px 12px', borderRadius: 4, fontFamily: 'monospace', color: '#ffa502', fontSize: 11 }}>
              {sessionId ? sessionId.slice(0, 8) + '...' : '-'}
            </span>
          </div>
        </div>

        <button
          onClick={connected ? disconnect : connect}
          style={{ background: '#00d9ff', color: '#1a1a2e', border: 'none', padding: '10px 20px', borderRadius: 6, cursor: 'pointer', fontWeight: 'bold' }}
        >
          {connected ? 'Disconnect' : 'Connect'}
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 20 }}>

        {/* Robotic Voice Panel */}
        <div style={{ background: '#16213e', borderRadius: 8, padding: 15 }}>
          <h2 style={{ fontSize: 14, textTransform: 'uppercase', color: '#888', marginBottom: 10, letterSpacing: 1 }}>
            🤖 Robotic Voice (Test Interruption)
          </h2>

          <div style={{ marginBottom: 15 }}>
            <button
              onClick={voiceConnected ? disconnectVoice : connectVoice}
              disabled={!connected}
              style={{
                background: voiceConnected ? '#ff4757' : '#2ed573',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: 6,
                cursor: connected ? 'pointer' : 'not-allowed',
                fontWeight: 'bold',
                marginRight: 10
              }}
            >
              {voiceConnected ? 'Disconnect Voice' : 'Connect Voice'}
            </button>
          </div>

          <textarea
            value={textToSpeak}
            onChange={e => setTextToSpeak(e.target.value)}
            placeholder="Enter text for robotic voice..."
            disabled={!voiceConnected}
            style={{
              width: '100%',
              height: 80,
              background: '#0f0f1a',
              border: '1px solid #333',
              borderRadius: 6,
              padding: 10,
              color: '#eee',
              fontFamily: 'inherit',
              marginBottom: 10
            }}
          />

          <div style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
            <button
              onClick={speak}
              disabled={!voiceConnected || speaking || narrating}
              style={{
                flex: 1,
                background: speaking ? '#ffa502' : (voiceConnected ? '#00d9ff' : '#555'),
                color: '#1a1a2e',
                border: 'none',
                padding: '12px 20px',
                borderRadius: 6,
                cursor: voiceConnected && !speaking && !narrating ? 'pointer' : 'not-allowed',
                fontWeight: 'bold'
              }}
            >
              {speaking ? '🔊 Speaking...' : '🎤 WS Speak'}
            </button>
            <button
              onClick={narrateViaHttp}
              disabled={!voiceConnected || speaking || narrating}
              style={{
                flex: 1,
                background: narrating ? '#ffa502' : (voiceConnected ? '#2ed573' : '#555'),
                color: '#1a1a2e',
                border: 'none',
                padding: '12px 20px',
                borderRadius: 6,
                cursor: voiceConnected && !speaking && !narrating ? 'pointer' : 'not-allowed',
                fontWeight: 'bold'
              }}
            >
              {narrating ? '📡 Sending...' : '📡 HTTP Narrate'}
            </button>
          </div>

          {audioProgress && (
            <div style={{ background: '#0f0f1a', padding: 10, borderRadius: 6, fontSize: 12, color: '#888' }}>
              Audio chunks: {audioProgress.chunks} {audioProgress.total > 0 && `/ ${audioProgress.total}`}
            </div>
          )}

          {narrateResponse && (
            <div style={{
              padding: 10,
              background: '#0f0f1a',
              borderRadius: 6,
              fontSize: 12,
              marginBottom: 10,
              color: narrateResponse.status === 'ok' ? '#2ed573' : '#ff4757'
            }}>
              <div>HTTP Narrate → Pod: <strong>{narrateResponse.hostname}</strong></div>
              {narrateResponse.error && <div>Error: {narrateResponse.error}</div>}
              <div style={{ marginTop: 5, color: narrateResponse.hostname === wsHostname ? '#2ed573' : '#ff4757' }}>
                {narrateResponse.hostname === wsHostname
                  ? '✓ Same pod as Voice WS - affinity working!'
                  : '✗ Different pod - affinity broken!'}
              </div>
            </div>
          )}

          <div style={{ marginTop: 10, padding: 10, background: '#0f3460', borderRadius: 6, fontSize: 12, color: '#888' }}>
            <div><strong>🎤 WS Speak:</strong> Send text directly over Voice WebSocket</div>
            <div><strong>📡 HTTP Narrate:</strong> Send text via HTTP POST - tests session affinity!</div>
            <div style={{ marginTop: 8 }}>💡 If HTTP Narrate fails with "No active voice call", it means the HTTP request went to a different pod than your Voice WebSocket.</div>
          </div>
        </div>

        {/* Messages Panel */}
        <div style={{ background: '#16213e', borderRadius: 8, padding: 15 }}>
          <h2 style={{ fontSize: 14, textTransform: 'uppercase', color: '#888', marginBottom: 10, letterSpacing: 1 }}>
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
                borderLeft: `3px solid ${
                  msg.type === 'warning' ? '#ff4757' :
                  msg.type === 'voice' ? '#ffa502' :
                  msg.type === 'error' ? '#ff4757' :
                  '#00d9ff'
                }`
              }}>
                <div style={{ color: '#888', fontSize: 11, marginBottom: 4 }}>
                  {msg.timestamp.toLocaleTimeString()} | {msg.type} | pod: {msg.hostname}
                </div>
                <div style={{ color: '#fff' }}>{msg.content}</div>
              </div>
            ))}
          </div>
        </div>

        {/* HTTP Affinity Panel */}
        <div style={{ background: '#16213e', borderRadius: 8, padding: 15 }}>
          <h2 style={{ fontSize: 14, textTransform: 'uppercase', color: '#888', marginBottom: 10, letterSpacing: 1 }}>
            HTTP Affinity Test
          </h2>

          <textarea
            value={inputValue}
            onChange={e => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message... (Cmd+Enter to send)"
            disabled={!connected}
            style={{
              width: '100%',
              height: 60,
              background: '#0f0f1a',
              border: '1px solid #333',
              borderRadius: 6,
              padding: 10,
              color: '#eee',
              fontFamily: 'inherit',
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
            {sending ? 'Sending...' : 'Send via HTTP'}
          </button>

          <div style={{ padding: 10, background: '#0f0f1a', borderRadius: 6, fontFamily: 'monospace', fontSize: 12, color: '#888' }}>
            {httpResponse ? (
              <>
                <div>HTTP pod: <strong>{httpResponse.hostname}</strong></div>
                <div>WS pod: <strong>{wsHostname}</strong></div>
                <div style={{ marginTop: 8, color: affinityMatch ? '#2ed573' : '#ff4757', fontWeight: 'bold' }}>
                  {affinityMatch ? '✓ Affinity working!' : '✗ Affinity broken!'}
                </div>
              </>
            ) : 'Send a message to test affinity'}
          </div>
        </div>
      </div>
    </div>
  )
}
