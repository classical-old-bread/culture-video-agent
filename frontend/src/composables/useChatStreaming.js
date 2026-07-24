import { ref } from 'vue'
import { streamChatMessage } from '../api/chat'

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

export function useChatStreaming({
  input,
  loading: externalLoading,
  messages,
  syncActiveSession,
  buildConversationContext,
  getLatestAssistantCalligraphyText,
  scrollToBottom,
  stopLocalMedia,
  stopCurrentAudio,
  speakText,
  queueStreamingSpeech,
  isSpeaking,
  speechQueuePlaying,
  localMediaPlaying,
  isInterruptCommand,
  shortVideoCharacterProfile,
  beforeSend,
  afterSend,
  onInterrupt,
}) {
  const loading = externalLoading || ref(false)
  const currentStreamController = ref(null)
  const currentResponseShouldSpeak = ref(true)

  async function appendStreamingText(index, text) {
    // 后端 delta 可能一次返回较长片段，这里分块追加，让界面呈现更自然的流式效果。
    if (!text) return

    for (let position = 0; position < text.length; position += 3) {
      messages.value[index].content += text.slice(position, position + 3)
      await scrollToBottom()
      await wait(12)
    }
  }

  function isAssistantOutputActive() {
    // 统一判断“助手是否正在输出”，供语音打断、持续监听和播放控制复用。
    return (
      loading.value ||
      isSpeaking.value ||
      speechQueuePlaying.value ||
      localMediaPlaying.value ||
      Boolean(currentStreamController.value)
    )
  }

  function interruptAssistant({ force = false } = {}) {
    // 打断要同时停止文本流、TTS 队列和本地媒体，避免多个输出源继续播放。
    if (
      !force &&
      !loading.value &&
      !isSpeaking.value &&
      !speechQueuePlaying.value &&
      !currentStreamController.value
    ) {
      return
    }

    stopCurrentAudio()
    stopLocalMedia()

    if (currentStreamController.value) {
      currentStreamController.value.abort()
      currentStreamController.value = null
    }

    loading.value = false
    input.value = ''
    onInterrupt?.()

    const lastMessage = messages.value[messages.value.length - 1]
    if (lastMessage?.role === 'assistant' && !lastMessage.content.trim()) {
      lastMessage.content = '已打断当前回答。'
      syncActiveSession()
    }
  }

  async function sendMessage(forcedText = '') {
    const text = (forcedText || input.value).trim()
    if (!text) return

    if (isInterruptCommand?.(text)) {
      interruptAssistant({ force: true })
      return
    }

    if (loading.value) return

    beforeSend?.()

    stopLocalMedia()
    stopCurrentAudio()
    const conversationContext = buildConversationContext()
    const calligraphySourceText = getLatestAssistantCalligraphyText()

    const assistantMessage = {
      id: Date.now() + 1,
      role: 'assistant',
      content: '',
      responseType: 'agent',
      videos: [],
      autoPlay: false,
      calligraphyImageUrl: '',
      calligraphyMissingChars: [],
      calligraphySelection: null,
      shortVideoProject: null,
      sources: [],
      toolCalls: [],
    }

    messages.value.push({
      id: Date.now(),
      role: 'user',
      content: text,
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
    messages.value.push(assistantMessage)
    const assistantIndex = messages.value.length - 1
    syncActiveSession({ updateTitle: true })
    input.value = ''
    loading.value = true
    currentResponseShouldSpeak.value = true
    const controller = new AbortController()
    currentStreamController.value = controller
    await scrollToBottom()

    try {
      await streamChatMessage(text, {
        signal: controller.signal,
        onMeta(data) {
          // meta 事件携带结构化结果，例如媒体、书法图片、短剧项目和工具计划。
          const shouldPlayVideo = Boolean(data.auto_play)
          const mediaResources = Array.isArray(data.videos) ? data.videos : []
          if (data.speak === false) {
            currentResponseShouldSpeak.value = false
            stopCurrentAudio()
          }
          messages.value[assistantIndex].responseType = data.type || messages.value[assistantIndex].responseType
          messages.value[assistantIndex].videos = mediaResources
          messages.value[assistantIndex].autoPlay = shouldPlayVideo
          messages.value[assistantIndex].calligraphyImageUrl = data.calligraphy_image_url || ''
          messages.value[assistantIndex].calligraphyMissingChars = Array.isArray(data.calligraphy_missing_chars)
            ? data.calligraphy_missing_chars
            : []
          messages.value[assistantIndex].calligraphySelection = data.calligraphy_selection || null
          messages.value[assistantIndex].shortVideoProject = data.short_video_project || null
          messages.value[assistantIndex].sources = Array.isArray(data.sources) ? data.sources : []
          if (Array.isArray(data.tool_calls) && data.tool_calls.length) {
            messages.value[assistantIndex].toolCalls = data.tool_calls
          }
          if (shouldPlayVideo) {
            currentResponseShouldSpeak.value = false
            stopCurrentAudio()
          }
        },
        onTool(data) {
          // tool 事件只更新工具轨迹状态，不直接改写回答正文。
          const existing = messages.value[assistantIndex].toolCalls || []
          const sameToolStep = (item) => {
            if (data.step_id || item.step_id) {
              return item.step_id === data.step_id
            }
            return item.tool_name === data.tool_name
          }
          const next = existing.map((item) =>
            sameToolStep(item)
              ? { ...item, ...data, status: data.status || item.status }
              : item
          )
          if (!next.some(sameToolStep)) {
            next.push(data)
          }
          messages.value[assistantIndex].toolCalls = next
          syncActiveSession()
        },
        async onDelta(content) {
          // delta 是正文增量；如果当前回答允许朗读，同步推入 TTS 队列。
          await appendStreamingText(assistantIndex, content)
          if (currentResponseShouldSpeak.value) {
            queueStreamingSpeech(content)
          }
        },
        onDone() {
          // done 表示本轮 SSE 结束；此时落盘会话并刷新 TTS 队列。
          if (!messages.value[assistantIndex].content.trim()) {
            messages.value[assistantIndex].content = '暂时没有生成有效回答，请稍后再试。'
          }
          syncActiveSession()
          if (currentResponseShouldSpeak.value) {
            queueStreamingSpeech('', { flush: true })
          }
        },
      }, {
        conversationContext,
        calligraphySourceText,
        calligraphyStyle: '',
        calligraphyAuthor: '',
        shortVideoCharacterProfile: shortVideoCharacterProfile?.value || '',
      })
    } catch (error) {
      const wasAborted = controller.signal.aborted || error?.name === 'AbortError'
      messages.value[assistantIndex].content = wasAborted
        ? messages.value[assistantIndex].content || '已打断当前回答。'
        : error?.message || '请求失败，请检查后端服务、DeepSeek API 或 MySQL 连接状态。'
      messages.value[assistantIndex].videos = []
      messages.value[assistantIndex].autoPlay = false
      messages.value[assistantIndex].calligraphyImageUrl = ''
      messages.value[assistantIndex].calligraphyMissingChars = []
      messages.value[assistantIndex].calligraphySelection = null
      messages.value[assistantIndex].shortVideoProject = null
      messages.value[assistantIndex].sources = []
      messages.value[assistantIndex].toolCalls = []
      syncActiveSession()
      if (!wasAborted) {
        speakText(messages.value[assistantIndex].content)
      }
    } finally {
      if (currentStreamController.value === controller) {
        currentStreamController.value = null
      }
      loading.value = false
      afterSend?.()
      await scrollToBottom()
    }
  }

  return {
    loading,
    currentStreamController,
    sendMessage,
    interruptAssistant,
    isAssistantOutputActive,
  }
}
