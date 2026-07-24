import { ref } from 'vue'

const STORAGE_KEY = 'culture-video-agent-sessions'
const welcomeMessage = '你好，我是传统文化导览员。你可以问传统节日、诗词典故、地方民俗，也可以生成书法作品、短剧脚本或查找本地民歌媒体。'

function createWelcomeMessage() {
  return {
    id: Date.now() + Math.random(),
    role: 'assistant',
    content: welcomeMessage,
    responseType: 'text',
    videos: [],
    autoPlay: false,
    calligraphyImageUrl: '',
    calligraphyMissingChars: [],
    calligraphySelection: null,
    shortVideoProject: null,
    sources: [],
    toolCalls: [],
  }
}

function normalizeMessage(message) {
  return {
    responseType: message.role === 'assistant' ? 'text' : 'text',
    videos: [],
    autoPlay: false,
    calligraphyImageUrl: '',
    calligraphyMissingChars: [],
    calligraphySelection: null,
    shortVideoProject: null,
    sources: [],
    toolCalls: [],
    ...message,
    autoPlay: false,
  }
}

function normalizeSession(session) {
  return {
    ...session,
    messages: Array.isArray(session.messages)
      ? session.messages.map(normalizeMessage)
      : [createWelcomeMessage()],
  }
}

function createSession(title = '新的文化对话') {
  const now = Date.now()
  return {
    id: `${now}-${Math.random().toString(16).slice(2)}`,
    title,
    updatedAt: now,
    messages: [createWelcomeMessage()],
  }
}

function loadSessions() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    if (Array.isArray(parsed) && parsed.length) {
      return parsed.map(normalizeSession)
    }
  } catch {
    window.localStorage.removeItem(STORAGE_KEY)
  }
  return [createSession()]
}

function isCalligraphySelectionMessage(message) {
  const content = message.content || ''
  const hasBlockingCalligraphyTool = (message.toolCalls || []).some((tool) => {
    const name = tool.tool_name || tool.toolName
    return name === 'calligraphy_render_tool' && tool.status === 'needs_input'
  })
  return Boolean(message.calligraphySelection) ||
    hasBlockingCalligraphyTool ||
    content.startsWith('生成书法前') ||
    content.startsWith('已选择') ||
    content.includes('还需要选择书法') ||
    content.includes('请选择书法风格') ||
    content.includes('选择书法风格') ||
    content.includes('选择书法作者') ||
    content.includes('没有提供要书写') ||
    content.includes('请先告诉我您想用')
}

export function useChatSessions({ input, loading, scrollToBottom }) {
  const sessions = ref(loadSessions())
  const activeSessionId = ref(sessions.value[0].id)
  const activeSessionTitle = ref(sessions.value[0].title)
  const messages = ref([...sessions.value[0].messages])

  function saveSessions() {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions.value.map(normalizeSession)))
  }

  function syncActiveSession({ updateTitle = false } = {}) {
    const session = sessions.value.find((item) => item.id === activeSessionId.value)
    if (!session) return

    session.messages = messages.value.map(normalizeMessage)
    session.updatedAt = Date.now()

    if (updateTitle) {
      const firstUserMessage = messages.value.find((message) => message.role === 'user')
      if (firstUserMessage?.content) {
        session.title = firstUserMessage.content.slice(0, 18)
        activeSessionTitle.value = session.title
      }
    }

    sessions.value = [...sessions.value].sort((a, b) => b.updatedAt - a.updatedAt)
    saveSessions()
  }

  function createNewSession() {
    if (loading.value) return
    const session = createSession()
    sessions.value = [session, ...sessions.value]
    activeSessionId.value = session.id
    activeSessionTitle.value = session.title
    messages.value = session.messages.map(normalizeMessage)
    input.value = ''
    saveSessions()
    scrollToBottom()
  }

  function selectSession(sessionId) {
    if (loading.value || sessionId === activeSessionId.value) return
    const session = sessions.value.find((item) => item.id === sessionId)
    if (!session) return
    activeSessionId.value = session.id
    activeSessionTitle.value = session.title
    messages.value = session.messages.map(normalizeMessage)
    input.value = ''
    scrollToBottom()
  }

  function deleteSession(sessionId) {
    if (loading.value) return

    const remainingSessions = sessions.value.filter((item) => item.id !== sessionId)
    if (!remainingSessions.length) {
      const session = createSession()
      sessions.value = [session]
      activeSessionId.value = session.id
      activeSessionTitle.value = session.title
      messages.value = session.messages.map(normalizeMessage)
      input.value = ''
      saveSessions()
      scrollToBottom()
      return
    }

    sessions.value = remainingSessions

    if (sessionId === activeSessionId.value) {
      const nextSession = remainingSessions[0]
      activeSessionId.value = nextSession.id
      activeSessionTitle.value = nextSession.title
      messages.value = nextSession.messages.map(normalizeMessage)
      input.value = ''
      scrollToBottom()
    }

    saveSessions()
  }

  function clearCurrentSession() {
    if (loading.value) return
    messages.value = [createWelcomeMessage()]
    const session = sessions.value.find((item) => item.id === activeSessionId.value)
    if (session) {
      session.title = '新的文化对话'
      activeSessionTitle.value = session.title
    }
    syncActiveSession()
  }

  function formatSessionTime(timestamp) {
    const date = new Date(timestamp)
    return `${String(date.getMonth() + 1).padStart(2, '0')}/${String(date.getDate()).padStart(2, '0')}`
  }

  function pushSystemMessage(content) {
    messages.value.push({
      id: Date.now() + Math.random(),
      role: 'assistant',
      content,
      responseType: 'text',
      videos: [],
      autoPlay: false,
      calligraphyImageUrl: '',
      calligraphyMissingChars: [],
      calligraphySelection: null,
      shortVideoProject: null,
      sources: [],
      toolCalls: [],
    })
    syncActiveSession()
    scrollToBottom()
  }

  function getLatestAssistantText() {
    for (let index = messages.value.length - 1; index >= 0; index -= 1) {
      const message = messages.value[index]
      if (
        message.role === 'assistant' &&
        message.content &&
        message.content !== welcomeMessage &&
        !isCalligraphySelectionMessage(message) &&
        !message.calligraphyImageUrl &&
        !message.videos?.length
      ) {
        return message.content.trim()
      }
    }
    return ''
  }

  function buildConversationContext() {
    return messages.value
      .filter((message) => message.content && message.content !== welcomeMessage)
      .slice(-6)
      .map((message) => `${message.role === 'user' ? '用户' : '助手'}：${message.content}`)
      .join('\n')
      .slice(-6000)
  }

  return {
    welcomeMessage,
    sessions,
    activeSessionId,
    activeSessionTitle,
    messages,
    syncActiveSession,
    createNewSession,
    selectSession,
    deleteSession,
    clearCurrentSession,
    formatSessionTime,
    pushSystemMessage,
    buildConversationContext,
    getLatestAssistantCalligraphyText: getLatestAssistantText,
  }
}
