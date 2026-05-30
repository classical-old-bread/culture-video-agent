import { ref } from 'vue'

const STORAGE_KEY = 'culture-video-agent-sessions'
const welcomeMessage = '你好，我是文化问答助手。你可以询问传统节日、诗词典故、地方民俗，也可以直接提到具体民歌、地方曲艺或书法生成需求。'

function createWelcomeMessage() {
  return {
    id: Date.now() + Math.random(),
    role: 'assistant',
    content: welcomeMessage,
    videos: [],
    autoPlay: false,
    toolCalls: [],
  }
}

function disablePersistedAutoPlay(message) {
  return {
    ...message,
    autoPlay: false,
  }
}

function disableSessionAutoPlay(session) {
  return {
    ...session,
    messages: Array.isArray(session.messages)
      ? session.messages.map(disablePersistedAutoPlay)
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
      return parsed.map(disableSessionAutoPlay)
    }
  } catch {
    window.localStorage.removeItem(STORAGE_KEY)
  }
  return [createSession()]
}

function isSelectionPrompt(content = '') {
  return content.startsWith('生成书法前')
}

function isCalligraphyPromptContent(content = '') {
  return (
    content.startsWith('生成书法前') ||
    content.includes('生成书法前需要') ||
    content.includes('当前可选风格') ||
    content.includes('可选作者') ||
    isSelectionPrompt(content)
  )
}

export function useChatSessions({ input, loading, scrollToBottom }) {
  const sessions = ref(loadSessions())
  const activeSessionId = ref(sessions.value[0].id)
  const activeSessionTitle = ref(sessions.value[0].title)
  const messages = ref([...sessions.value[0].messages])

  function saveSessions() {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions.value.map(disableSessionAutoPlay)))
  }

  function syncActiveSession({ updateTitle = false } = {}) {
    const session = sessions.value.find((item) => item.id === activeSessionId.value)
    if (!session) return

    session.messages = messages.value.map(disablePersistedAutoPlay)
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
    messages.value = session.messages.map(disablePersistedAutoPlay)
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
    messages.value = session.messages.map(disablePersistedAutoPlay)
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
      messages.value = session.messages.map(disablePersistedAutoPlay)
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
      messages.value = nextSession.messages.map(disablePersistedAutoPlay)
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
      videos: [],
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
        !isSelectionPrompt(message.content) &&
        !isCalligraphyPromptContent(message.content) &&
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
