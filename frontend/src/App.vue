<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand-block">
        <div class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24">
            <path d="M12 3 14.7 9.3 21 12l-6.3 2.7L12 21l-2.7-6.3L3 12l6.3-2.7L12 3Z" />
          </svg>
        </div>
        <div>
          <div class="brand-title">秦风民歌大模型</div>
          <div class="brand-subtitle">Culture Agent</div>
        </div>
      </div>

      <nav class="sidebar-nav" aria-label="功能导航">
        <button
          v-for="item in navItems"
          :key="item.label"
          type="button"
          class="nav-item"
          :class="{ active: activeView === item.view, muted: item.muted }"
          @click="selectNavItem(item)"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path :d="item.icon" />
          </svg>
          <span>{{ item.label }}</span>
          <small v-if="item.badge">{{ item.badge }}</small>
        </button>
      </nav>

      <section class="session-panel" aria-label="会话列表">
        <div class="session-panel-header">
          <span>对话</span>
          <button type="button" :disabled="loading" @click="createNewSession">新建</button>
        </div>

        <div class="session-list">
          <div
            v-for="session in sessions"
            :key="session.id"
            class="session-item"
            :class="{ active: session.id === activeSessionId }"
          >
            <button
              type="button"
              class="session-select"
              :disabled="loading"
              @click="selectSession(session.id)"
            >
              <span>{{ session.title }}</span>
              <small>{{ formatSessionTime(session.updatedAt) }}</small>
            </button>
            <button
              type="button"
              class="session-delete"
              :disabled="loading"
              :aria-label="`删除对话：${session.title}`"
              @click.stop="deleteSession(session.id)"
            >
              ×
            </button>
          </div>
        </div>
      </section>

      <div class="sidebar-card">
        <span>当前能力</span>
        <strong>文化问答 · 视频检索</strong>
        <p>输入问题后自动识别文化主题与陕北民歌视频需求。</p>
      </div>
    </aside>

    <main v-if="activeView === 'chat'" class="chat-page">
      <header class="topbar">
        <div>
          <div class="product-name">文化问答</div>
          <p>传统文化知识解答与陕北民歌视频</p>
        </div>
        <div class="status-pill" :class="{ active: loading || isListening || isSpeaking || radioModeActive }">
          <span class="status-dot" aria-hidden="true"></span>
          {{ radioModeActive ? '麦克风监听' : isListening ? '正在聆听' : isSpeaking ? '朗读中' : loading ? '生成中' : '服务就绪' }}
        </div>
      </header>

      <section class="output-zone">
        <div class="output-header">
          <div>
            <strong>对话记录</strong>
            <span>{{ activeSessionTitle }}</span>
          </div>
          <button type="button" class="clear-button" :disabled="loading" @click="clearCurrentSession">清空当前对话</button>
        </div>

        <div ref="messageListRef" class="message-list" aria-live="polite">
          <ChatMessage
            v-for="message in messages"
            :key="message.id"
            :role="message.role"
            :content="message.content"
            :videos="message.videos"
            :auto-play="message.autoPlay"
            :calligraphy-image-url="message.calligraphyImageUrl"
            :tool-calls="message.toolCalls"
            @video-play="handleLocalMediaPlay"
            @video-pause="handleLocalMediaStop"
            @video-ended="handleLocalMediaStop"
          />

          <div v-if="loading" class="message-row assistant">
            <div class="message-bubble loading-bubble">
              <span class="loader" aria-hidden="true"></span>
              正在生成回答...
            </div>
          </div>
        </div>
      </section>

      <form class="composer" @submit.prevent="handleSend">
        <label class="sr-only" for="chat-input">输入问题</label>
        <textarea
          id="chat-input"
          v-model="input"
          placeholder="询问传统文化、诗词民俗，或输入具体民歌、地方曲艺等相关问题"
          rows="2"
          maxlength="1000"
          :disabled="loading"
          @keydown.enter.exact.prevent="handleSend"
        />

        <div class="composer-actions">
          <span class="char-count">{{ input.length }}/1000</span>
          <button
            type="button"
            class="voice-button"
            :class="{ active: isListening }"
            :disabled="loading"
            :title="isListening ? '松开发送语音内容' : '按住说话，松开发送'"
            :aria-label="isListening ? '松开发送语音内容' : '按住说话，松开发送'"
            @pointerdown.prevent="startVoiceInput"
            @pointerup.prevent="finishVoiceInput"
            @pointercancel.prevent="finishVoiceInput"
            @keydown.space.prevent="startVoiceInput"
            @keyup.space.prevent="finishVoiceInput"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3Z" />
              <path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6" />
            </svg>
          </button>
          <button
            type="button"
            class="radio-mode-button"
            :class="{ active: radioModeActive }"
            :disabled="loading"
            :title="radioModeActive ? '关闭麦克风监听' : '开启麦克风持续监听'"
            :aria-label="radioModeActive ? '关闭麦克风监听' : '开启麦克风持续监听'"
            @click="toggleRadioMode"
          >
            监听
          </button>
          <button type="submit" class="send-button" :disabled="loading || !input.trim()" aria-label="发送消息">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="m5 12 14-7-4 14-3-6-7-1Z" />
              <path d="m12 13 7-8" />
            </svg>
            发送
          </button>
        </div>
      </form>
    </main>

    <main v-else class="knowledge-page">
      <header class="topbar">
        <div>
          <div class="product-name">书法字库</div>
          <p>书法字库字形展示</p>
        </div>
        <div class="status-pill" :class="{ active: galleryLoading }">
          <span class="status-dot" aria-hidden="true"></span>
          {{ galleryLoading ? '加载字库' : `${galleryItems.length} 个字形` }}
        </div>
      </header>

      <section class="glyph-showcase" aria-label="书法字库轮播">
        <div class="glyph-showcase-header">
          <div>
            <strong>字库长卷</strong>
            <span>精选书法字形，铺展传统笔墨之美</span>
          </div>
        </div>

        <div v-if="galleryItems.length" class="glyph-marquee-stack">
          <div
            v-for="(row, rowIndex) in galleryRows"
            :key="rowIndex"
            class="glyph-marquee"
            :class="{ reverse: rowIndex % 2 === 1 }"
            :style="{ '--row-duration': `${38 + rowIndex * 7}s` }"
          >
            <div class="glyph-track">
              <div
                v-for="(item, index) in row"
                :key="`${item.style}-${item.author}-${item.char}-${rowIndex}-${index}`"
                class="glyph-tile"
              >
                <img :src="absoluteGalleryImageUrl(item.image_url)" :alt="item.caption" />
                <span>{{ item.style }} · {{ item.author }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="glyph-empty">
          {{ galleryLoading ? '正在读取书法字库...' : '暂无可展示字形，请检查书法字库配置。' }}
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { streamChatMessage } from './api/chat'
import ChatMessage from './components/ChatMessage.vue'
import { useCalligraphyGallery } from './composables/useCalligraphyGallery'
import { useChatSessions } from './composables/useChatSessions'
import { compactRepeatedVoiceText, createCloudRecognition } from './composables/useCloudRecognition'
import { useSpeechPlayback } from './composables/useSpeechPlayback'

const input = ref('')
const loading = ref(false)
const currentStreamController = ref(null)
const currentResponseShouldSpeak = ref(true)
const messageListRef = ref(null)
const recognitionRef = ref(null)
const pendingVoiceText = ref('')
const voiceIsPressed = ref(false)
const voiceStopRequested = ref(false)
const radioModeActive = ref(false)
const radioHasVoice = ref(false)
const radioSubmitting = ref(false)
const radioRecognitionStarting = ref(false)
const radioAsrRestartDelay = ref(500)
const lastRadioAsrErrorAt = ref(0)
const radioLastVoiceAt = ref(0)
const lastSubmittedVoiceText = ref('')
const lastSubmittedVoiceAt = ref(0)
const audioStreamRef = ref(null)
const audioContextRef = ref(null)
const analyserRef = ref(null)
const radioFrameRef = ref(0)
const radioRestartTimerRef = ref(0)
const radioSubmitTimerRef = ref(0)

const VOICE_HOTKEY_CODES = new Set(['F8', 'F9', 'MediaRecord'])
const RADIO_VOLUME_THRESHOLD = 0.004
const RADIO_SILENCE_MS = 3000
const RADIO_TEXT_IDLE_MS = 1600
const RADIO_DUPLICATE_IGNORE_MS = 9000
const RADIO_ASR_RESTART_MIN_MS = 500
const RADIO_ASR_RESTART_MAX_MS = 15000
const RADIO_ASR_ERROR_MESSAGE_INTERVAL_MS = 12000
const INTERRUPT_COMMAND_PATTERNS = [
  /^停止(播放|回答|回复|朗读|播报|生成|输出)?$/,
  /^停(止|下|掉|住)?(播放|回答|回复|朗读|播报|生成|输出)?$/,
  /^暂停(播放|回答|回复|朗读|播报|生成|输出)?$/,
  /^取消(播放|回答|回复|朗读|播报|生成|输出)?$/,
  /^中断(播放|回答|回复|朗读|播报|生成|输出)?$/,
  /^打断(播放|回答|回复|朗读|播报|生成|输出)?$/,
  /^别(播放|回答|回复|朗读|播报|输出|说|讲)了?$/,
  /^不要(播放|回答|回复|朗读|播报|输出|说|讲)了?$/,
]
const INTERRUPT_COMMAND_CONTAINS_PATTERNS = [
  /停止(播放|回答|回复|朗读|播报|生成|输出)/,
  /停住(播放|回答|回复|朗读|播报|生成|输出)/,
  /暂停(播放|回答|回复|朗读|播报|生成|输出)/,
  /中断(播放|回答|回复|朗读|播报|生成|输出)/,
  /打断(播放|回答|回复|朗读|播报|生成|输出)/,
  /别(播放|回答|回复|朗读|播报|输出|说|讲)了?/,
  /不要(播放|回答|回复|朗读|播报|输出|说|讲)了?/,
]

const navItems = [
  {
    label: '文化问答',
    view: 'chat',
    icon: 'M5 6h14v9H8l-3 3V6Z',
  },
  {
    label: '书法字库',
    view: 'knowledge',
    icon: 'M6 4h12v16H6V4Zm3 4h6M9 12h6M9 16h4',
  },
]

const {
  activeView,
  galleryItems,
  galleryLoading,
  galleryRows,
  absoluteGalleryImageUrl,
  selectNavItem,
} = useCalligraphyGallery()

const {
  isSpeaking,
  localMediaPlaying,
  speechQueuePlaying,
  stopCurrentAudio,
  stopLocalMedia,
  handleLocalMediaPlay,
  handleLocalMediaStop,
  speakText,
  queueStreamingSpeech,
} = useSpeechPlayback({
  onSpeechIdle: () => scheduleRadioRecognitionRestart(),
})

const {
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
  getLatestAssistantCalligraphyText,
} = useChatSessions({ input, loading, scrollToBottom })

async function scrollToBottom() {
  await nextTick()
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight
  }
}

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

async function appendStreamingText(index, text) {
  if (!text) return

  for (let position = 0; position < text.length; position += 3) {
    messages.value[index].content += text.slice(position, position + 3)
    await scrollToBottom()
    await wait(12)
  }
}

function stopCurrentRecognition({ abort = false } = {}) {
  if (!recognitionRef.value) return

  try {
    if (abort) {
      recognitionRef.value.abort()
    } else {
      recognitionRef.value.stop()
    }
  } catch {
    recognitionRef.value = null
    isListening.value = false
  }
}

const isListening = ref(false)

function isFatalAsrError(detail = '') {
  return /未配置|未开通|没有流式 ASR 权限|没有流式ASR权限|resource not granted|requested resource not granted|code['":=\s]+403|连接被拒绝|HTTP 400|麦克风权限|NotAllowed/i.test(detail)
}

function normalizeVoiceText(text) {
  return text.replace(/\s+/g, '').trim()
}

function normalizeCommandText(text) {
  return normalizeVoiceText(text).replace(/[，。！？!?,.；;：:、]/g, '')
}

function normalizeInterruptCommandText(text) {
  return normalizeCommandText(text)
    .replace(/^(请帮我|请给我|麻烦你|请你|能不能|能否|帮我|给我|麻烦|可以|请)+/, '')
    .replace(/(一下|一下吧|吧|呢|可以吗|好不好|行不行|好吗|谢谢)$/g, '')
}

function isInterruptCommand(text) {
  const normalized = normalizeInterruptCommandText(text)
  return Boolean(normalized) && INTERRUPT_COMMAND_PATTERNS.some((pattern) => pattern.test(normalized))
}

function containsInterruptCommand(text) {
  const normalized = normalizeInterruptCommandText(text)
  return Boolean(normalized) && INTERRUPT_COMMAND_CONTAINS_PATTERNS.some((pattern) => pattern.test(normalized))
}

function shouldInterruptFromTranscript(text) {
  return isInterruptCommand(text) || (isAssistantOutputActive() && containsInterruptCommand(text))
}

function isAssistantOutputActive() {
  return (
    loading.value ||
    isSpeaking.value ||
    speechQueuePlaying.value ||
    localMediaPlaying.value ||
    Boolean(currentStreamController.value)
  )
}

function isRecentlySubmittedVoice(text) {
  const normalized = normalizeVoiceText(text)
  if (!normalized) return false

  return (
    normalized === lastSubmittedVoiceText.value &&
    Date.now() - lastSubmittedVoiceAt.value < RADIO_DUPLICATE_IGNORE_MS
  )
}

function markVoiceSubmitted(text) {
  lastSubmittedVoiceText.value = normalizeVoiceText(text)
  lastSubmittedVoiceAt.value = Date.now()
}

function interruptAssistant({ force = false } = {}) {
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
  window.clearTimeout(radioSubmitTimerRef.value)

  if (currentStreamController.value) {
    currentStreamController.value.abort()
    currentStreamController.value = null
  }

  loading.value = false
  radioSubmitting.value = false
  pendingVoiceText.value = ''
  input.value = ''
  radioHasVoice.value = false
  radioLastVoiceAt.value = 0

  const lastMessage = messages.value[messages.value.length - 1]
  if (lastMessage?.role === 'assistant' && !lastMessage.content.trim()) {
    lastMessage.content = '已打断当前回答。'
    syncActiveSession()
  }

  scheduleRadioRecognitionRestart()
}

function handleInterruptCommand() {
  stopCurrentRecognition({ abort: true })
  stopLocalMedia()
  interruptAssistant({ force: true })
  pendingVoiceText.value = ''
  input.value = ''
}

async function startVoiceInput(event) {
  if (loading.value) return
  if (radioModeActive.value) {
    pushSystemMessage('麦克风持续监听已开启；如需使用页面按住说话按钮，请先关闭监听。')
    return
  }
  if (isListening.value || recognitionRef.value) return

  if (event?.currentTarget?.setPointerCapture && event.pointerId !== undefined) {
    try {
      event.currentTarget.setPointerCapture(event.pointerId)
    } catch {
    }
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    pushSystemMessage('当前浏览器无法读取麦克风，请确认浏览器和权限设置。')
    return
  }

  stopLocalMedia()
  stopCurrentAudio()

  voiceIsPressed.value = true
  voiceStopRequested.value = false
  pendingVoiceText.value = ''

  try {
    const recognition = await createCloudRecognition({
      onStart() {
        isListening.value = true
      },
      onText(transcript) {
        if (!transcript) return
        if (shouldInterruptFromTranscript(transcript)) {
          voiceIsPressed.value = false
          voiceStopRequested.value = false
          handleInterruptCommand()
          return
        }

        pendingVoiceText.value = transcript
        input.value = transcript
      },
      async onEnd() {
        isListening.value = false
        recognitionRef.value = null

        const text = compactRepeatedVoiceText(pendingVoiceText.value).trim()
        const shouldSend = voiceStopRequested.value && text

        voiceIsPressed.value = false
        voiceStopRequested.value = false

        if (shouldSend) {
          await nextTick()
          await sendMessage(text)
        }
      },
      onError(detail) {
        pushSystemMessage(detail || '火山语音识别失败，请稍后重试。')
      },
    })
    recognitionRef.value = recognition
  } catch (error) {
    recognitionRef.value = null
    isListening.value = false
    voiceIsPressed.value = false
    pushSystemMessage(error?.name === 'NotAllowedError'
      ? '浏览器没有获得麦克风权限，请允许麦克风后再试。'
      : '火山语音识别启动失败，请稍后重试。')
  }
}

function finishVoiceInput() {
  if (!voiceIsPressed.value && !isListening.value) return

  voiceIsPressed.value = false
  voiceStopRequested.value = true

  if (recognitionRef.value) {
    try {
      recognitionRef.value.stop()
    } catch {
      recognitionRef.value = null
      isListening.value = false
    }
    return
  }

  const text = compactRepeatedVoiceText(pendingVoiceText.value).trim()
  if (text) {
    sendMessage(text)
  }
}

function isEditableTarget(target) {
  if (!(target instanceof HTMLElement)) return false
  const tagName = target.tagName.toLowerCase()
  return tagName === 'input' || tagName === 'textarea' || target.isContentEditable
}

function isVoiceActivationEvent(event) {
  const isSpacePushToTalk = event.code === 'Space' && !isEditableTarget(event.target)
  const isVoiceHotkey = VOICE_HOTKEY_CODES.has(event.code)
  return isSpacePushToTalk || isVoiceHotkey
}

function handleGlobalVoiceKeyDown(event) {
  if (radioModeActive.value) {
    if (isVoiceActivationEvent(event)) event.preventDefault()
    return
  }

  if (!isVoiceActivationEvent(event) || event.repeat) return
  event.preventDefault()
  startVoiceInput()
}

function handleGlobalVoiceKeyUp(event) {
  if (radioModeActive.value) {
    if (isVoiceActivationEvent(event)) event.preventDefault()
    return
  }

  if (!isVoiceActivationEvent(event)) return
  event.preventDefault()
  finishVoiceInput()
}

async function toggleRadioMode() {
  if (radioModeActive.value) {
    stopRadioMode()
    return
  }

  await startRadioMode()
}

async function startRadioMode() {
  if (loading.value || radioModeActive.value) return

  if (!navigator.mediaDevices?.getUserMedia) {
    pushSystemMessage('当前浏览器无法读取麦克风音量，不能开启麦克风持续监听。')
    return
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    })
    const AudioContext = window.AudioContext || window.webkitAudioContext
    const audioContext = new AudioContext()
    const source = audioContext.createMediaStreamSource(stream)
    const analyser = audioContext.createAnalyser()

    analyser.fftSize = 1024
    source.connect(analyser)

    audioStreamRef.value = stream
    audioContextRef.value = audioContext
    analyserRef.value = analyser
    radioModeActive.value = true
    radioSubmitting.value = false
    radioRecognitionStarting.value = false
    radioAsrRestartDelay.value = RADIO_ASR_RESTART_MIN_MS
    lastRadioAsrErrorAt.value = 0
    radioLastVoiceAt.value = 0
    pendingVoiceText.value = ''

    stopLocalMedia()
    stopCurrentAudio()

    startRadioRecognition()
    monitorRadioVolume()
  } catch {
    pushSystemMessage('无法开启麦克风持续监听，请确认浏览器已经允许麦克风权限，并检查麦克风是否被系统识别为输入设备。')
  }
}

function stopRadioMode() {
  radioModeActive.value = false
  radioSubmitting.value = false
  radioRecognitionStarting.value = false
  radioAsrRestartDelay.value = RADIO_ASR_RESTART_MIN_MS
  radioHasVoice.value = false
  radioLastVoiceAt.value = 0
  window.clearTimeout(radioRestartTimerRef.value)
  window.clearTimeout(radioSubmitTimerRef.value)

  if (radioFrameRef.value) {
    window.cancelAnimationFrame(radioFrameRef.value)
    radioFrameRef.value = 0
  }

  stopCurrentRecognition({ abort: true })

  if (audioStreamRef.value) {
    audioStreamRef.value.getTracks().forEach((track) => track.stop())
    audioStreamRef.value = null
  }

  if (audioContextRef.value) {
    audioContextRef.value.close()
    audioContextRef.value = null
  }

  analyserRef.value = null
}

function startRadioRecognition() {
  if (!radioModeActive.value || recognitionRef.value || radioRecognitionStarting.value) return

  radioRecognitionStarting.value = true

  createCloudRecognition({
    stream: audioStreamRef.value,
    onStart() {
      isListening.value = true
      radioRecognitionStarting.value = false
    },
    onText(transcript) {
      if (!transcript) return
      radioAsrRestartDelay.value = RADIO_ASR_RESTART_MIN_MS
      if (shouldInterruptFromTranscript(transcript)) {
        handleInterruptCommand()
        return
      }

      if (isAssistantOutputActive() || radioSubmitting.value) {
        pendingVoiceText.value = ''
        input.value = ''
        return
      }

      if (isRecentlySubmittedVoice(transcript)) {
        pendingVoiceText.value = ''
        input.value = ''
        return
      }

      pendingVoiceText.value = transcript
      input.value = transcript
      scheduleRadioTextSubmit()
    },
    onEnd() {
      isListening.value = false
      recognitionRef.value = null
      radioRecognitionStarting.value = false
      scheduleRadioRecognitionRestart()
    },
    onError(detail) {
      const now = Date.now()
      if (isFatalAsrError(detail || '')) {
        pushSystemMessage(/未配置|未开通|没有流式 ASR 权限|resource not granted|403/i.test(detail || '')
          ? detail
          : '浏览器没有获得麦克风权限，请允许麦克风后再试。')
        stopRadioMode()
        return
      }
      if (now - lastRadioAsrErrorAt.value > RADIO_ASR_ERROR_MESSAGE_INTERVAL_MS) {
        pushSystemMessage(detail || '火山语音识别失败，正在稍后重试。')
        lastRadioAsrErrorAt.value = now
      }
      radioAsrRestartDelay.value = Math.min(
        RADIO_ASR_RESTART_MAX_MS,
        Math.max(3000, radioAsrRestartDelay.value * 2),
      )
    },
  }).then((recognition) => {
    radioRecognitionStarting.value = false
    if (!radioModeActive.value) {
      recognition.abort()
      return
    }
    recognitionRef.value = recognition
  }).catch((error) => {
    radioRecognitionStarting.value = false
    recognitionRef.value = null
    isListening.value = false
    if (error?.name === 'NotAllowedError') {
      pushSystemMessage('浏览器没有获得麦克风权限，请允许麦克风后再试。')
      stopRadioMode()
      return
    }
    radioAsrRestartDelay.value = Math.min(
      RADIO_ASR_RESTART_MAX_MS,
      Math.max(3000, radioAsrRestartDelay.value * 2),
    )
    scheduleRadioRecognitionRestart()
  })
}

function scheduleRadioRecognitionRestart() {
  window.clearTimeout(radioRestartTimerRef.value)
  if (!radioModeActive.value) return

  radioRestartTimerRef.value = window.setTimeout(() => {
    if (!radioModeActive.value) return
    if (recognitionRef.value || radioRecognitionStarting.value) {
      scheduleRadioRecognitionRestart()
      return
    }
    startRadioRecognition()
  }, radioAsrRestartDelay.value)
}

function scheduleRadioTextSubmit() {
  window.clearTimeout(radioSubmitTimerRef.value)
  if (!radioModeActive.value || isAssistantOutputActive()) return

  radioSubmitTimerRef.value = window.setTimeout(() => {
    const text = compactRepeatedVoiceText(pendingVoiceText.value).trim()
    if (
      text &&
      radioModeActive.value &&
      !isAssistantOutputActive() &&
      !radioSubmitting.value &&
      !isRecentlySubmittedVoice(text)
    ) {
      submitRadioText(text)
    }
  }, RADIO_TEXT_IDLE_MS)
}

function monitorRadioVolume() {
  if (!radioModeActive.value || !analyserRef.value) return

  const data = new Uint8Array(analyserRef.value.fftSize)

  const tick = () => {
    if (!radioModeActive.value || !analyserRef.value) return

    analyserRef.value.getByteTimeDomainData(data)
    let sum = 0

    for (const value of data) {
      const normalized = (value - 128) / 128
      sum += normalized * normalized
    }

    const volume = Math.sqrt(sum / data.length)
    const now = Date.now()

    if (isAssistantOutputActive()) {
      radioHasVoice.value = false
      radioLastVoiceAt.value = 0
      window.clearTimeout(radioSubmitTimerRef.value)
      radioFrameRef.value = window.requestAnimationFrame(tick)
      return
    }

    if (volume > RADIO_VOLUME_THRESHOLD) {
      radioHasVoice.value = true
      radioLastVoiceAt.value = now
    }

    const text = compactRepeatedVoiceText(pendingVoiceText.value).trim()
    const hasFinishedSpeaking =
      radioHasVoice.value && text && radioLastVoiceAt.value && now - radioLastVoiceAt.value > RADIO_SILENCE_MS

    if (hasFinishedSpeaking && !isAssistantOutputActive() && !radioSubmitting.value && !isRecentlySubmittedVoice(text)) {
      submitRadioText(text)
    }

    radioFrameRef.value = window.requestAnimationFrame(tick)
  }

  radioFrameRef.value = window.requestAnimationFrame(tick)
}

async function submitRadioText(rawText) {
  const text = compactRepeatedVoiceText(rawText).trim()
  if (!text) return

  if (isInterruptCommand(text)) {
    handleInterruptCommand()
    return
  }

  if (isAssistantOutputActive() || radioSubmitting.value || isRecentlySubmittedVoice(text)) return

  window.clearTimeout(radioSubmitTimerRef.value)
  radioSubmitting.value = true
  radioHasVoice.value = false
  pendingVoiceText.value = ''
  input.value = ''
  markVoiceSubmitted(text)
  stopCurrentRecognition()

  try {
    await sendMessage(text)
  } finally {
    radioSubmitting.value = false
    scheduleRadioRecognitionRestart()
  }
}

async function handleSend() {
  await sendMessage()
}

async function sendMessage(forcedText = '') {
  const text = (forcedText || input.value).trim()
  if (!text) return

  if (isInterruptCommand(text)) {
    handleInterruptCommand()
    return
  }

  if (loading.value) return

  if (radioModeActive.value) {
    window.clearTimeout(radioSubmitTimerRef.value)
    stopCurrentRecognition({ abort: true })
  }

  stopLocalMedia()
  stopCurrentAudio()
  const conversationContext = buildConversationContext()
  const calligraphySourceText = getLatestAssistantCalligraphyText()

  const assistantMessage = {
    id: Date.now() + 1,
    role: 'assistant',
    content: '',
    videos: [],
    autoPlay: false,
    calligraphyImageUrl: '',
    toolCalls: [],
  }

  messages.value.push({
    id: Date.now(),
    role: 'user',
    content: text,
    videos: [],
    autoPlay: false,
    calligraphyImageUrl: '',
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
  if (radioModeActive.value) {
    scheduleRadioRecognitionRestart()
  }
  await scrollToBottom()

  try {
    await streamChatMessage(text, {
      signal: controller.signal,
      onMeta(data) {
        const shouldPlayVideo = Boolean(data.auto_play)
        const mediaResources = Array.isArray(data.videos) ? data.videos : []
        if (data.speak === false) {
          currentResponseShouldSpeak.value = false
          stopCurrentAudio()
        }
        messages.value[assistantIndex].videos = mediaResources
        messages.value[assistantIndex].autoPlay = shouldPlayVideo
        messages.value[assistantIndex].calligraphyImageUrl = data.calligraphy_image_url || ''
        if (Array.isArray(data.tool_calls) && data.tool_calls.length) {
          messages.value[assistantIndex].toolCalls = data.tool_calls
        }
        if (shouldPlayVideo) {
          currentResponseShouldSpeak.value = false
          stopCurrentAudio()
        }
      },
      onTool(data) {
        const existing = messages.value[assistantIndex].toolCalls || []
        const next = existing.map((item) =>
          item.tool_name === data.tool_name
            ? { ...item, status: data.status || item.status }
            : item
        )
        if (!next.some((item) => item.tool_name === data.tool_name)) {
          next.push(data)
        }
        messages.value[assistantIndex].toolCalls = next
        syncActiveSession()
      },
      async onDelta(content) {
        await appendStreamingText(assistantIndex, content)
        if (currentResponseShouldSpeak.value) {
          queueStreamingSpeech(content)
        }
      },
      onVideos(data) {
        const shouldPlayVideo = Boolean(data.auto_play)
        const mediaResources = Array.isArray(data.videos) ? data.videos : []
        messages.value[assistantIndex].videos = mediaResources
        messages.value[assistantIndex].autoPlay = shouldPlayVideo
        if (shouldPlayVideo && mediaResources.length) {
          currentResponseShouldSpeak.value = false
          stopCurrentAudio()
        }
        syncActiveSession()
        scrollToBottom()
      },
      onDone() {
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
    })
  } catch (error) {
    const wasAborted = controller.signal.aborted || error?.name === 'AbortError'
    messages.value[assistantIndex].content = wasAborted
      ? messages.value[assistantIndex].content || '已打断当前回答。'
      : error?.message || '请求失败，请检查后端服务、DeepSeek API 或 MySQL 连接状态。'
    messages.value[assistantIndex].videos = []
    messages.value[assistantIndex].autoPlay = false
    messages.value[assistantIndex].calligraphyImageUrl = ''
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
    if (radioModeActive.value) {
      radioSubmitting.value = false
      scheduleRadioRecognitionRestart()
    }
    await scrollToBottom()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleGlobalVoiceKeyDown)
  window.addEventListener('keyup', handleGlobalVoiceKeyUp)
  startRadioMode()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleGlobalVoiceKeyDown)
  window.removeEventListener('keyup', handleGlobalVoiceKeyUp)
  stopRadioMode()
  if (recognitionRef.value) {
    recognitionRef.value.abort()
  }
  stopLocalMedia()
  stopCurrentAudio()
})
</script>
