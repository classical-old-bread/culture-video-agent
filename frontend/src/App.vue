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
          <div class="brand-title">文化 Agent 工作台</div>
          <div class="brand-subtitle">Culture Agent</div>
        </div>
      </div>

      <nav class="sidebar-nav" aria-label="功能导航">
        <button
          v-for="item in navItems"
          :key="item.label"
          type="button"
          class="nav-item"
          :class="{ active: activeView === item.view }"
          @click="selectNavItem(item)"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path :d="item.icon" />
          </svg>
          <span>{{ item.label }}</span>
        </button>
      </nav>

      <section class="session-panel" aria-label="会话列表">
        <div class="session-panel-header">
          <span>会话</span>
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
              :aria-label="`删除会话：${session.title}`"
              @click.stop="deleteSession(session.id)"
            >
              ×
            </button>
          </div>
        </div>
      </section>

      <div class="sidebar-card">
        <span>当前能力</span>
        <strong>问答 · 书法 · 短剧 · 媒体</strong>
        <p>对话框负责理解需求和媒体播放，工作区负责展示书法、短剧、来源和工具轨迹。</p>
      </div>
    </aside>

    <main v-if="activeView === 'chat'" class="chat-page">
      <header class="topbar">
        <div>
          <div class="product-name">传统文化多工具 Agent</div>
          <p>一个入口处理文化知识、书法生成、短剧脚本和本地媒体检索。</p>
        </div>
        <div class="status-pill" :class="{ active: loading || isListening || isSpeaking || radioModeActive }">
          <span class="status-dot" aria-hidden="true"></span>
          {{ statusText }}
        </div>
      </header>

      <div class="workspace-grid" :class="{ 'panel-open': workspacePanelOpen }">
        <section class="output-zone">
          <div class="output-header">
            <div>
              <strong>对话记录</strong>
              <span>{{ activeSessionTitle }}</span>
            </div>
            <div class="output-actions">
              <button type="button" class="clear-button" :disabled="loading" @click="clearCurrentSession">
                清空
              </button>
              <button
                type="button"
                class="workspace-toggle"
                :class="{ active: workspacePanelOpen || hasWorkspaceContent }"
                @click="workspacePanelOpen = !workspacePanelOpen"
              >
                工作区
                <span v-if="workspaceBadge">{{ workspaceBadge }}</span>
              </button>
            </div>
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
              :calligraphy-selection="message.calligraphySelection"
              :tool-calls="message.toolCalls"
              @video-play="handleLocalMediaPlay"
              @video-pause="handleLocalMediaStop"
              @video-ended="handleLocalMediaStop"
              @calligraphy-option="handleCalligraphyOption"
            />

            <div v-if="loading" class="message-row assistant">
              <div class="message-bubble loading-bubble">
                <span class="loader" aria-hidden="true"></span>
                正在生成回答...
              </div>
            </div>
          </div>
        </section>

        <TaskPanel
          v-if="workspacePanelOpen"
          :message="latestAssistantMessage"
          :loading="loading"
          @video-play="handleLocalMediaPlay"
          @video-pause="handleLocalMediaStop"
          @video-ended="handleLocalMediaStop"
          @calligraphy-option="handleCalligraphyOption"
        />
      </div>

      <form class="composer" @submit.prevent="handleSend">
        <label class="sr-only" for="chat-input">输入问题</label>
        <textarea
          id="chat-input"
          v-model="input"
          placeholder="可以问传统文化、生成书法、创作成语短剧，或查找本地民歌视频"
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

    <main v-else-if="activeView === 'short_video'" class="short-video-page">
      <header class="topbar">
        <div>
          <div class="product-name">短剧创作工作台</div>
          <p>独立生成五镜头分镜、对白和 AI 视频提示词。</p>
        </div>
        <div class="status-pill" :class="{ active: shortVideoLoading }">
          <span class="status-dot" aria-hidden="true"></span>
          {{ shortVideoLoading ? '短剧生成中' : shortVideoProject ? '脚本就绪' : '等待创作' }}
        </div>
      </header>

      <div class="short-video-workspace">
        <section class="short-video-control" aria-label="短剧创作控制台">
          <div class="short-video-section-heading">
            <div>
              <span>Creative Console</span>
              <strong>创作控制台</strong>
            </div>
          </div>

          <label class="field-block">
            <span>短剧主题</span>
            <textarea
              v-model="shortVideoTopic"
              rows="5"
              maxlength="300"
              placeholder="输入任意短剧主题，例如：雨天回家、校园小误会、企鹅女孩买早餐、魔法便利店、端午节传说"
            />
          </label>

          <section class="character-config standalone">
            <div class="character-config-header">
              <div>
                <strong>主角一致性设定</strong>
                <span>参考图只用于你记录角色方向，当前生成主要依赖下方文字设定。</span>
              </div>
              <label class="character-upload">
                上传图
                <input type="file" accept="image/*" @change="handleCharacterImageUpload" />
              </label>
            </div>
            <div class="character-config-body">
              <div v-if="shortVideoCharacterImage" class="character-preview">
                <img :src="shortVideoCharacterImage" alt="短剧主角参考图" />
                <button type="button" @click="clearCharacterImage">移除</button>
              </div>
              <div v-else class="character-drop-placeholder">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M4 17 9 12l4 4 2-2 5 5M6 5h12v14H6V5Zm3 4h.01" />
                </svg>
                <span>可上传参考图</span>
              </div>
              <textarea
                v-model="shortVideoCharacterProfile"
                rows="6"
                maxlength="1500"
                placeholder="例如：穿企鹅连体服的小女孩，黑色齐刘海短发，浅蓝色十字发夹。所有镜头保持同一脸型、发型、服装和配饰。"
                @blur="saveCharacterProfile"
              />
            </div>
          </section>

          <section v-if="shortVideoPrototypeFrames.length" class="prototype-frame-panel">
            <div class="prototype-frame-header">
              <div>
                <strong>原型画面</strong>
                <span>从原型帧库中选择一帧作为本次渲染的构图和画风参考。</span>
              </div>
              <button
                type="button"
                :disabled="!selectedPrototypeFrameUrl"
                @click="selectedPrototypeFrameUrl = ''"
              >
                清除
              </button>
            </div>
            <div class="prototype-frame-list">
              <button
                v-for="frame in shortVideoPrototypeFrames"
                :key="frame.url"
                type="button"
                class="prototype-frame-option"
                :class="{ active: selectedPrototypeFrameUrl === frame.url }"
                @click="selectedPrototypeFrameUrl = frame.url"
              >
                <img :src="frame.url" :alt="`原型帧 ${frame.name}`" />
                <span>{{ frame.name.replace(/\.[^.]+$/, '') }}</span>
              </button>
            </div>
          </section>

          <div class="short-video-actions">
            <button
              type="button"
              class="short-video-generate"
              :disabled="shortVideoLoading || !shortVideoTopic.trim()"
              @click="generateShortVideo"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M5 5h14v10H5V5Zm3 14h8M12 15v4M9 9l5 3-5 3V9Z" />
              </svg>
              {{ shortVideoLoading ? 'Agent 创作中' : '生成短剧方案' }}
            </button>
            <button type="button" class="short-video-secondary" :disabled="shortVideoLoading" @click="resetShortVideo">
              清空
            </button>
          </div>

          <p v-if="shortVideoError" class="short-video-error">{{ shortVideoError }}</p>
        </section>

        <section class="short-video-result" aria-label="短剧生成结果">
          <nav class="short-video-tabs" aria-label="短剧结果视图">
            <button
              v-for="tab in shortVideoTabs"
              :key="tab.id"
              type="button"
              :class="{ active: shortVideoActiveTab === tab.id }"
              @click="shortVideoActiveTab = tab.id"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path :d="tab.icon" />
              </svg>
              {{ tab.label }}
            </button>
          </nav>

          <div class="short-video-result-body">
            <div v-if="!shortVideoProject && !shortVideoLoading" class="short-video-empty">
              <strong>等待短剧方案</strong>
              <p>输入主题后会生成主题表达、主角设定、五镜头分镜和可复制的视频提示词。</p>
            </div>

            <div v-else-if="shortVideoLoading" class="short-video-empty">
              <span class="loader" aria-hidden="true"></span>
              <strong>正在生成短剧方案</strong>
              <p>{{ shortVideoDraftContent || '短视频创作 Agent 正在组织分镜、对白和提示词。' }}</p>
            </div>

            <div v-else-if="shortVideoActiveTab === 'overview'" class="short-video-overview">
              <section class="short-video-summary-card">
                <span>标题</span>
                <strong>{{ shortVideoProject.title }}</strong>
              </section>
              <div class="short-video-meta-grid">
                <section>
                  <span>主题</span>
                  <strong>{{ shortVideoProject.topic }}</strong>
                </section>
                <section>
                  <span>受众</span>
                  <strong>{{ shortVideoProject.audience }}</strong>
                </section>
              </div>
              <section class="short-video-note">
                <span>主题表达</span>
                <p>{{ shortVideoProject.moral }}</p>
              </section>
              <section class="short-video-note">
                <span>统一画风</span>
                <p>{{ shortVideoProject.visual_style }}</p>
              </section>
              <section class="short-video-note">
                <span>主角</span>
                <p>{{ shortVideoProject.main_character }}</p>
              </section>
            </div>

            <div v-else-if="shortVideoActiveTab === 'shots'" class="short-video-shot-grid">
              <article
                v-for="shot in shortVideoProject.shots"
                :key="shot.shot"
                class="short-video-shot-card"
              >
                <div class="shot-card-header">
                  <strong>镜头 {{ shot.shot }}</strong>
                  <span>{{ shot.duration }}</span>
                </div>
                <dl class="shot-detail">
                  <div>
                    <dt>场景</dt>
                    <dd>{{ shot.scene }}</dd>
                  </div>
                  <div>
                    <dt>镜头</dt>
                    <dd>{{ shot.camera }}</dd>
                  </div>
                  <div>
                    <dt>画面</dt>
                    <dd>{{ shot.action }}</dd>
                  </div>
                  <div>
                    <dt>台词</dt>
                    <dd>{{ shot.dialogue }}</dd>
                  </div>
                  <div>
                    <dt>衔接</dt>
                    <dd>{{ shot.continuity }}</dd>
                  </div>
                </dl>
              </article>
            </div>

            <div v-else class="short-video-prompts">
              <div class="section-heading">
                <span>AI 视频提示词</span>
                <button type="button" class="panel-copy-button" @click="copyShortVideoPrompts">复制全部</button>
              </div>
              <article
                v-for="shot in shortVideoProject.shots"
                :key="`prompt-${shot.shot}`"
                class="prompt-box"
              >
                <div>
                  <span>镜头 {{ shot.shot }}</span>
                  <div class="prompt-actions">
                    <button type="button" @click="copyText(shot.video_prompt)">复制</button>
                    <button
                      type="button"
                      :disabled="isShotRendering(shot.shot)"
                      @click="confirmRenderShot(shot)"
                    >
                      {{ renderButtonLabel(shot.shot) }}
                    </button>
                  </div>
                </div>
                <p>{{ shot.video_prompt }}</p>
                <div v-if="shortVideoRenderTasks[shot.shot]" class="render-status-card">
                  <div>
                    <strong>{{ renderStatusLabel(shortVideoRenderTasks[shot.shot]) }}</strong>
                    <span v-if="shortVideoRenderTasks[shot.shot].progress">
                      {{ shortVideoRenderTasks[shot.shot].progress }}%
                    </span>
                  </div>
                  <video
                    v-if="shortVideoRenderTasks[shot.shot].video_url"
                    :src="shortVideoRenderTasks[shot.shot].video_url"
                    controls
                  ></video>
                  <p v-if="shortVideoRenderTasks[shot.shot].error">
                    {{ shortVideoRenderTasks[shot.shot].error }}
                  </p>
                </div>
              </article>
              <section v-if="shortVideoProject.negative_prompt" class="short-video-note negative">
                <span>负面提示词</span>
                <p>{{ shortVideoProject.negative_prompt }}</p>
              </section>
            </div>
          </div>
        </section>
      </div>
    </main>

    <main v-else-if="activeView === 'knowledge'" class="knowledge-page">
      <header class="topbar">
        <div>
          <div class="product-name">书法字库</div>
          <p>浏览当前可用的书法字形资源。</p>
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
            <span>精选书法字形，用于生成书法作品。</span>
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
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import ChatMessage from './components/ChatMessage.vue'
import TaskPanel from './components/TaskPanel.vue'
import {
  fetchShortVideoPrototypeFrames,
  fetchShortVideoRenderStatus,
  streamChatMessage,
  submitShortVideoRender,
} from './api/chat'
import { useAssistantCommands } from './composables/useAssistantCommands'
import { useCalligraphyGallery } from './composables/useCalligraphyGallery'
import { useChatSessions } from './composables/useChatSessions'
import { useChatStreaming } from './composables/useChatStreaming'
import { useRadioMode } from './composables/useRadioMode'
import { useSpeechPlayback } from './composables/useSpeechPlayback'
import { useVoiceInput } from './composables/useVoiceInput'

const input = ref('')
const loading = ref(false)
const messageListRef = ref(null)
const recognitionRef = ref(null)
const isListening = ref(false)
const pendingVoiceText = ref('')
const radioModeActive = ref(false)
const workspacePanelOpen = ref(false)
const DEFAULT_CHARACTER_PROFILE = '穿企鹅连体服的小女孩，黑色齐刘海短发，浅蓝色十字发夹，黑灰企鹅帽，黄色企鹅嘴帽檐，白色圆肚皮，黄色脚蹼，银色拉链扣。所有镜头保持同一脸型、发型、服装、配饰和颜色。'
const shortVideoCharacterProfile = ref(window.localStorage.getItem('culture-agent-character-profile') || '')
const shortVideoCharacterImage = ref('')
const shortVideoTopic = ref('')
const shortVideoLoading = ref(false)
const shortVideoError = ref('')
const shortVideoProject = ref(null)
const shortVideoDraftContent = ref('')
const shortVideoToolCalls = ref([])
const shortVideoActiveTab = ref('overview')
const shortVideoRenderTasks = ref({})
const shortVideoPrototypeFrames = ref([])
const selectedPrototypeFrameUrl = ref('')

const navItems = [
  {
    label: 'Agent 对话',
    view: 'chat',
    icon: 'M5 6h14v9H8l-3 3V6Z',
  },
  {
    label: '短剧创作',
    view: 'short_video',
    icon: 'M5 5h14v14H5V5Zm4 4h2m2 0h2M9 13h6M9 16h4',
  },
  {
    label: '书法字库',
    view: 'knowledge',
    icon: 'M6 4h12v16H6V4Zm3 4h6M9 12h6M9 16h4',
  },
]

const shortVideoTabs = [
  {
    id: 'overview',
    label: '方案概览',
    icon: 'M5 5h14v14H5V5Zm4 4h6M9 12h6M9 15h4',
  },
  {
    id: 'shots',
    label: '五镜头分镜',
    icon: 'M4 6h16M4 12h16M4 18h16M8 4v16M16 4v16',
  },
  {
    id: 'prompts',
    label: '视频提示词',
    icon: 'M6 5h12v14H6V5Zm3 4h6M9 12h6M9 15h3',
  },
]

let scheduleRadioRecognitionRestart = () => {}
let beforeRadioChatSend = () => {}
let afterRadioChatSend = () => {}
let resetRadioPendingState = () => {}
let stopCurrentRecognition = () => {}
let isAssistantOutputActive = () => false

const {
  activeView,
  galleryItems,
  galleryLoading,
  galleryRows,
  absoluteGalleryImageUrl,
  selectNavItem,
} = useCalligraphyGallery()

async function scrollToBottom() {
  await nextTick()
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight
  }
}

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

const latestAssistantMessage = computed(() => {
  for (let index = messages.value.length - 1; index >= 0; index -= 1) {
    const message = messages.value[index]
    if (message.role === 'assistant') {
      return message
    }
  }
  return null
})

const hasWorkspaceContent = computed(() => {
  const message = latestAssistantMessage.value
  return Boolean(
    loading.value ||
    message?.shortVideoProject ||
    message?.calligraphySelection ||
    message?.calligraphyImageUrl ||
    message?.sources?.length
  )
})

const workspaceBadge = computed(() => {
  const message = latestAssistantMessage.value
  if (loading.value) return '处理中'
  if (message?.shortVideoProject) return '短剧'
  if (message?.calligraphyImageUrl || message?.calligraphySelection) return '书法'
  return ''
})

const statusText = computed(() => {
  if (radioModeActive.value) return '麦克风监听'
  if (isListening.value) return '正在聆听'
  if (isSpeaking.value) return '朗读中'
  if (loading.value) return '生成中'
  return '服务就绪'
})

const {
  isInterruptCommand,
  shouldInterruptFromTranscript,
  normalizeVoiceText,
} = useAssistantCommands({
  isAssistantOutputActive: () => isAssistantOutputActive(),
})

const {
  sendMessage,
  interruptAssistant,
  isAssistantOutputActive: chatOutputActive,
} = useChatStreaming({
  input,
  loading,
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
  beforeSend: () => beforeRadioChatSend(),
  afterSend: () => afterRadioChatSend(),
  onInterrupt: () => {
    resetRadioPendingState()
    scheduleRadioRecognitionRestart()
  },
})

isAssistantOutputActive = chatOutputActive

function handleInterruptCommand() {
  stopCurrentRecognition({ abort: true })
  stopLocalMedia()
  interruptAssistant({ force: true })
  pendingVoiceText.value = ''
  input.value = ''
  resetRadioPendingState()
}

const voiceInput = useVoiceInput({
  input,
  loading,
  radioModeActive,
  recognitionRef,
  isListening,
  pendingVoiceText,
  sendMessage,
  pushSystemMessage,
  stopLocalMedia,
  stopCurrentAudio,
  shouldInterruptFromTranscript,
  onInterruptCommand: handleInterruptCommand,
})

stopCurrentRecognition = voiceInput.stopCurrentRecognition

const radioMode = useRadioMode({
  input,
  loading,
  radioModeActive,
  recognitionRef,
  isListening,
  pendingVoiceText,
  sendMessage,
  pushSystemMessage,
  stopCurrentRecognition: (options) => stopCurrentRecognition(options),
  stopLocalMedia,
  stopCurrentAudio,
  isAssistantOutputActive,
  isInterruptCommand,
  shouldInterruptFromTranscript,
  normalizeVoiceText,
  onInterruptCommand: handleInterruptCommand,
})

scheduleRadioRecognitionRestart = radioMode.scheduleRadioRecognitionRestart
beforeRadioChatSend = radioMode.beforeChatSend
afterRadioChatSend = radioMode.afterChatSend
resetRadioPendingState = radioMode.resetRadioPendingState

const {
  startVoiceInput,
  finishVoiceInput,
  handleGlobalVoiceKeyDown,
  handleGlobalVoiceKeyUp,
} = voiceInput

const {
  toggleRadioMode,
  startRadioMode,
  stopRadioMode,
} = radioMode

async function handleSend() {
  await sendMessage()
}

async function handleCalligraphyOption(option) {
  if (!option || loading.value) return
  const text = option.type === 'author'
    ? `选择书法风格：${option.style || ''}，书法作者：${option.value}`
    : `选择书法风格：${option.value}`
  await sendMessage(text)
}

async function generateShortVideo() {
  const topic = shortVideoTopic.value.trim()
  if (!topic || shortVideoLoading.value) return

  shortVideoLoading.value = true
  shortVideoError.value = ''
  shortVideoProject.value = null
  shortVideoDraftContent.value = ''
  shortVideoToolCalls.value = []
  shortVideoRenderTasks.value = {}
  shortVideoActiveTab.value = 'overview'
  stopLocalMedia()
  stopCurrentAudio()

  try {
    await streamChatMessage(
      `请生成一个关于“${topic}”的五镜头通用短剧方案，题材不限，可以是日常生活、校园、治愈、奇幻、轻喜剧或用户主题本身；包含分镜、对白和 AI 视频提示词。优先保证视频稳定出片：每个镜头 3-5 秒，只做一个简单动作，使用固定中景或中远景，避免手部特写、快速转身、复杂奔跑和多人互动。`,
      {
        onMeta(data) {
          if (Array.isArray(data.tool_calls) && data.tool_calls.length) {
            shortVideoToolCalls.value = data.tool_calls
          }
          if (data.short_video_project) {
            shortVideoProject.value = data.short_video_project
          }
        },
        onTool(data) {
          const existing = shortVideoToolCalls.value || []
          const sameToolStep = (item) => {
            if (data.step_id || item.step_id) {
              return item.step_id === data.step_id
            }
            return item.tool_name === data.tool_name
          }
          const next = existing.map((item) =>
            sameToolStep(item)
              ? { ...item, ...data }
              : item
          )
          if (!next.some(sameToolStep)) {
            next.push(data)
          }
          shortVideoToolCalls.value = next
        },
        onDelta(content) {
          shortVideoDraftContent.value += content
        },
      },
      {
        shortVideoCharacterProfile: shortVideoCharacterProfile.value.trim(),
      }
    )
  } catch (error) {
    shortVideoError.value = error?.message || '短剧生成失败，请检查后端服务或模型配置。'
  } finally {
    shortVideoLoading.value = false
  }
}

function resetShortVideo() {
  shortVideoTopic.value = ''
  shortVideoError.value = ''
  shortVideoProject.value = null
  shortVideoDraftContent.value = ''
  shortVideoToolCalls.value = []
  shortVideoRenderTasks.value = {}
  shortVideoActiveTab.value = 'overview'
}

async function confirmRenderShot(shot) {
  if (!shot?.video_prompt || isShotRendering(shot.shot)) return
  const accepted = window.confirm(`确认调用视频生成 API 渲染镜头 ${shot.shot}？这一步可能产生 API 费用。`)
  if (!accepted) return

  const previousTask = shortVideoRenderTasks.value[shot.shot - 1]
  const previousTailFrameUrl = previousTask?.tail_frame_url || ''
  setRenderTask(shot.shot, {
    status: 'submitting',
    progress: 0,
    error: '',
    video_url: '',
    tail_frame_url: '',
  })

  try {
    const data = await submitShortVideoRender({
      prompt: shot.video_prompt,
      duration: parseShotDuration(shot.duration),
      previousTailFrameUrl,
      characterReferenceImage: shortVideoCharacterImage.value,
      prototypeReferenceFrameUrl: selectedPrototypeFrameUrl.value,
    })
    setRenderTask(shot.shot, {
      ...shortVideoRenderTasks.value[shot.shot],
      task_id: data.task_id,
      status: 'processing',
      duration: data.duration,
    })
    pollShotRenderStatus(shot.shot, data.task_id)
  } catch (error) {
    setRenderTask(shot.shot, {
      ...shortVideoRenderTasks.value[shot.shot],
      status: 'failed',
      error: error?.response?.data?.detail || error?.message || '视频渲染提交失败。',
    })
  }
}

async function pollShotRenderStatus(shotNumber, taskId) {
  if (!taskId) return
  try {
    const data = await fetchShortVideoRenderStatus(taskId)
    setRenderTask(shotNumber, {
      ...shortVideoRenderTasks.value[shotNumber],
      ...data,
      task_id: taskId,
    })
    if (!['success', 'failed'].includes(data.status)) {
      window.setTimeout(() => pollShotRenderStatus(shotNumber, taskId), 3000)
    }
  } catch (error) {
    setRenderTask(shotNumber, {
      ...shortVideoRenderTasks.value[shotNumber],
      task_id: taskId,
      status: 'failed',
      error: error?.response?.data?.detail || error?.message || '视频渲染状态查询失败。',
    })
  }
}

function setRenderTask(shotNumber, task) {
  shortVideoRenderTasks.value = {
    ...shortVideoRenderTasks.value,
    [shotNumber]: task,
  }
}

function isShotRendering(shotNumber) {
  const status = shortVideoRenderTasks.value[shotNumber]?.status
  return ['submitting', 'processing'].includes(status)
}

function renderButtonLabel(shotNumber) {
  const task = shortVideoRenderTasks.value[shotNumber]
  if (!task) return '确认生成'
  if (task.status === 'submitting') return '提交中'
  if (task.status === 'processing') return '生成中'
  if (task.status === 'success') return '重新生成'
  if (task.status === 'failed') return '重试生成'
  return '确认生成'
}

function renderStatusLabel(task) {
  const labels = {
    submitting: '正在提交渲染任务',
    processing: '视频生成中',
    success: '视频已生成',
    failed: '生成失败',
  }
  return labels[task?.status] || '等待生成'
}

function parseShotDuration(value) {
  const numbers = String(value || '').match(/\d+/g)?.map(Number) || []
  if (!numbers.length) return 5
  return Math.max(3, Math.min(5, Math.max(...numbers)))
}

function copyShortVideoPrompts() {
  if (!shortVideoProject.value) return
  const prompts = shortVideoProject.value.shots
    .map((shot) => `镜头${shot.shot}：${shot.video_prompt}`)
    .join('\n\n')
  copyText(`${prompts}\n\n负面提示词：${shortVideoProject.value.negative_prompt || ''}`.trim())
}

async function copyText(text) {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // Clipboard may be unavailable on non-secure origins.
  }
}

function saveCharacterProfile() {
  const value = shortVideoCharacterProfile.value.trim()
  if (value) {
    window.localStorage.setItem('culture-agent-character-profile', value)
  } else {
    window.localStorage.removeItem('culture-agent-character-profile')
  }
}

function handleCharacterImageUpload(event) {
  const file = event.target.files?.[0]
  if (!file) return

  const reader = new FileReader()
  reader.onload = () => {
    const dataUrl = String(reader.result || '')
    shortVideoCharacterImage.value = dataUrl
    if (!shortVideoCharacterProfile.value.trim()) {
      shortVideoCharacterProfile.value = DEFAULT_CHARACTER_PROFILE
      saveCharacterProfile()
    }
  }
  reader.readAsDataURL(file)
  event.target.value = ''
}

function clearCharacterImage() {
  shortVideoCharacterImage.value = ''
}

async function loadShortVideoPrototypeFrames() {
  try {
    shortVideoPrototypeFrames.value = await fetchShortVideoPrototypeFrames()
    if (!selectedPrototypeFrameUrl.value && shortVideoPrototypeFrames.value.length) {
      selectedPrototypeFrameUrl.value = shortVideoPrototypeFrames.value[0].url
    }
  } catch {
    shortVideoPrototypeFrames.value = []
    selectedPrototypeFrameUrl.value = ''
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleGlobalVoiceKeyDown)
  window.addEventListener('keyup', handleGlobalVoiceKeyUp)
  startRadioMode()
  loadShortVideoPrototypeFrames()
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
