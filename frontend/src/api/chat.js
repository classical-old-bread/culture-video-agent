import axios from 'axios'

const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000'
const STREAM_EVENT_HANDLERS = {
  meta: 'onMeta',
  tool: 'onTool',
  done: 'onDone',
}

function normalizeApiBaseUrl(value) {
  if (value === undefined) return DEFAULT_API_BASE_URL
  return value.replace(/\/$/, '')
}

function buildAsrWsUrl(apiBaseUrl) {
  if (apiBaseUrl) return `${apiBaseUrl.replace(/^http/, 'ws')}/api/asr/stream`

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/asr/stream`
}

export const API_BASE_URL = normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL)
export const ASR_WS_URL = buildAsrWsUrl(API_BASE_URL)

export function buildApiUrl(path) {
  return `${API_BASE_URL}${path}`
}

const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
})

function parseSseBlock(block) {
  let event = 'message'
  const dataLines = []

  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trimStart())
    }
  }

  return {
    event,
    data: dataLines.length ? JSON.parse(dataLines.join('\n')) : {},
  }
}

async function parseErrorResponse(response, fallbackMessage) {
  try {
    const data = await response.json()
    return data.detail || fallbackMessage
  } catch {
    return fallbackMessage
  }
}

async function handleStreamEvent(block, handlers) {
  if (!block.trim()) return

  const { event, data } = parseSseBlock(block)
  if (event === 'delta') {
    await handlers.onDelta?.(data.content || '')
    return
  }
  if (event === 'error') {
    throw new Error(data.detail || '流式输出失败。')
  }

  const handlerName = STREAM_EVENT_HANDLERS[event]
  await handlers[handlerName]?.(data)
}

async function readSseStream(response, handlers) {
  if (!response.body) {
    throw new Error('浏览器没有收到流式响应内容。')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() || ''

    for (const block of blocks) {
      await handleStreamEvent(block, handlers)
    }
  }

  if (buffer.trim()) {
    await handleStreamEvent(buffer, handlers)
  }
}

function buildChatPayload(message, options) {
  return {
    message,
    conversation_context: options.conversationContext || null,
    calligraphy_source_text: options.calligraphySourceText || null,
    calligraphy_style: options.calligraphyStyle || null,
    calligraphy_author: options.calligraphyAuthor || null,
    short_video_character_profile: options.shortVideoCharacterProfile || null,
  }
}

export async function sendChatMessage(message, options = {}) {
  const response = await http.post('/api/chat', buildChatPayload(message, options))
  return response.data
}

export async function streamChatMessage(message, handlers = {}, options = {}) {
  const response = await fetch(buildApiUrl('/api/chat/stream'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    signal: handlers.signal,
    body: JSON.stringify(buildChatPayload(message, options)),
  })

  if (!response.ok) {
    const detail = await parseErrorResponse(
      response,
      '请求失败，请确认后端服务、DeepSeek API 和 MySQL 配置是否正常。'
    )
    throw new Error(detail)
  }

  await readSseStream(response, handlers)
}

export async function synthesizeSpeech(text, options = {}) {
  const response = await fetch(buildApiUrl('/api/tts'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    signal: options.signal,
    body: JSON.stringify({ text }),
  })

  if (!response.ok) {
    const detail = await parseErrorResponse(response, '语音合成失败。')
    throw new Error(detail)
  }

  return response.blob()
}

export async function fetchCalligraphyGallery() {
  const response = await http.get('/api/calligraphy-gallery')
  return response.data.items || []
}

export async function submitShortVideoRender({
  prompt,
  duration = 5,
  previousTailFrameUrl = '',
  characterReferenceImage = '',
  prototypeReferenceFrameUrl = '',
}) {
  const response = await http.post('/api/short-video/render', {
    prompt,
    duration,
    previous_tail_frame_url: previousTailFrameUrl || null,
    character_reference_image_data_url: characterReferenceImage || null,
    prototype_reference_frame_url: prototypeReferenceFrameUrl || null,
  })
  return response.data
}

export async function fetchShortVideoPrototypeFrames() {
  const response = await http.get('/api/short-video/prototype-frames')
  return (response.data.items || []).map((item) => ({
    ...item,
    url: typeof item.url === 'string' && item.url.startsWith('/') ? buildApiUrl(item.url) : item.url,
  }))
}

export async function fetchShortVideoRenderStatus(taskId) {
  const response = await http.get(`/api/short-video/render/${encodeURIComponent(taskId)}`)
  return normalizeShortVideoRenderTask(response.data)
}

function normalizeShortVideoRenderTask(task) {
  for (const key of ['video_url', 'tail_frame_url']) {
    if (typeof task?.[key] === 'string' && task[key].startsWith('/')) {
      task[key] = buildApiUrl(task[key])
    }
  }
  return task
}
