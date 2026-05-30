import axios from 'axios'

const envApiBaseUrl = import.meta.env.VITE_API_BASE_URL

function normalizeApiBaseUrl(value) {
  if (value === undefined) return 'http://127.0.0.1:8000'
  return value.replace(/\/$/, '')
}

function buildAsrWsUrl(apiBaseUrl) {
  if (apiBaseUrl) return `${apiBaseUrl.replace(/^http/, 'ws')}/api/asr/stream`

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/asr/stream`
}

export const API_BASE_URL = normalizeApiBaseUrl(envApiBaseUrl)
export const ASR_WS_URL = buildAsrWsUrl(API_BASE_URL)

const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000
})

function parseSseBlock(block) {
  const lines = block.split('\n')
  let event = 'message'
  const dataLines = []

  for (const line of lines) {
    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  }

  if (!dataLines.length) {
    return { event, data: {} }
  }

  return {
    event,
    data: JSON.parse(dataLines.join('\n'))
  }
}

export async function streamChatMessage(message, handlers = {}, options = {}) {
  // The chat endpoint streams SSE blocks over fetch so the UI can render tool events and answer deltas incrementally.
  const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    signal: handlers.signal,
    body: JSON.stringify({
      message,
      conversation_context: options.conversationContext || null,
      calligraphy_source_text: options.calligraphySourceText || null,
      calligraphy_style: options.calligraphyStyle || null,
      calligraphy_author: options.calligraphyAuthor || null
    })
  })

  if (!response.ok) {
    let detail = '?????????????DeepSeek API ? MySQL ???????'
    try {
      const data = await response.json()
      detail = data.detail || detail
    } catch {
      // Keep the generic message when the backend does not return JSON.
    }
    throw new Error(detail)
  }

  if (!response.body) {
    throw new Error('??????????????')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // Network chunks do not align with SSE boundaries, so keep the trailing partial block in buffer.
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() || ''

    for (const block of blocks) {
      if (!block.trim()) continue
      const { event, data } = parseSseBlock(block)

      if (event === 'meta') await handlers.onMeta?.(data)
      if (event === 'tool') await handlers.onTool?.(data)
      if (event === 'delta') await handlers.onDelta?.(data.content || '')
      if (event === 'videos') await handlers.onVideos?.(data)
      if (event === 'error') throw new Error(data.detail || '???????')
      if (event === 'done') await handlers.onDone?.()
    }
  }
}

export async function synthesizeSpeech(text, options = {}) {
  const response = await fetch(`${API_BASE_URL}/api/tts`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    signal: options.signal,
    body: JSON.stringify({ text })
  })

  if (!response.ok) {
    let detail = '???????'
    try {
      const data = await response.json()
      detail = data.detail || detail
    } catch {
      // Keep the generic message when the backend does not return JSON.
    }
    throw new Error(detail)
  }

  return response.blob()
}

export async function fetchCalligraphyGallery() {
  const response = await http.get('/api/calligraphy-gallery')
  return response.data.items || []
}
