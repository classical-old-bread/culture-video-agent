<template>
  <div class="message-row" :class="role">
    <div v-if="role === 'assistant'" class="message-avatar" aria-hidden="true">
      <svg viewBox="0 0 24 24">
        <path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v11a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5v-11Z" />
        <path d="M8 9h8M8 12h8M8 15h5" />
      </svg>
    </div>

    <div class="message-bubble">
      <details v-if="role === 'assistant' && normalizedToolCalls.length" class="message-tool-trace">
        <summary>
          <span>工具思考轨迹</span>
          <small>{{ completedToolCount }}/{{ normalizedToolCalls.length }} 步</small>
        </summary>
        <div class="message-tool-list">
          <div
            v-for="(tool, index) in normalizedToolCalls"
            :key="`${tool.name}-${tool.stepId || index}`"
            class="message-tool-item"
            :class="tool.status"
          >
            <div>
              <strong>{{ tool.agentName }} · {{ tool.displayName }}</strong>
              <span>{{ tool.statusText }}</span>
            </div>
            <p v-if="tool.summary">{{ tool.summary }}</p>
            <p v-if="tool.detail">{{ tool.detail }}</p>
          </div>
        </div>
      </details>

      <div class="message-content">
        <template v-for="(part, index) in contentParts" :key="index">
          <a
            v-if="part.type === 'link'"
            class="message-link"
            :href="part.text"
            target="_blank"
            rel="noopener noreferrer"
          >{{ part.text }}</a>
          <span v-else>{{ part.text }}</span>
        </template>
      </div>

      <div v-if="hasSelection" class="calligraphy-choice">
        <div v-if="styleOptions.length" class="choice-group">
          <span class="choice-label">选择书法风格</span>
          <div class="calligraphy-options">
            <button
              v-for="option in styleOptions"
              :key="`style-${option.value}`"
              type="button"
              class="calligraphy-option"
              :class="{ active: option.value === activeStyle }"
              @click="handleStyleOption(option)"
            >
              {{ option.label }}
            </button>
          </div>
        </div>

        <div v-if="authorOptions.length" class="choice-group">
          <span class="choice-label">选择书法作者</span>
          <div class="calligraphy-options">
            <button
              v-for="option in authorOptions"
              :key="`author-${option.style || activeStyle}-${option.value}`"
              type="button"
              class="calligraphy-option"
              :class="{ active: option.value === activeAuthor }"
              @click="handleAuthorOption(option)"
            >
              {{ option.label }}
            </button>
          </div>
        </div>
      </div>

      <div v-if="calligraphyImageUrl" class="calligraphy-result">
        <img :src="absoluteCalligraphyUrl" alt="书法作品" />
      </div>

      <div v-if="videos && videos.length" class="message-media-list">
        <div class="media-summary-header">
          <span>已找到 {{ videos.length }} 个媒体资源</span>
          <small>可在对话中播放</small>
        </div>
        <VideoCard
          v-for="(video, index) in videos"
          :key="video.id"
          :video="video"
          :auto-play="autoPlay && index === 0"
          @play="emit('video-play')"
          @pause="emit('video-pause')"
          @ended="emit('video-ended')"
        />
      </div>
    </div>

    <div v-if="role === 'user'" class="message-avatar user-avatar" aria-hidden="true">
      <svg viewBox="0 0 24 24">
        <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z" />
        <path d="M5 20a7 7 0 0 1 14 0" />
      </svg>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { API_BASE_URL } from '../api/chat'
import { useCalligraphySelection } from '../composables/useCalligraphySelection'
import VideoCard from './VideoCard.vue'

const props = defineProps({
  role: {
    type: String,
    required: true
  },
  content: {
    type: String,
    required: true
  },
  videos: {
    type: Array,
    default: () => []
  },
  autoPlay: {
    type: Boolean,
    default: false
  },
  calligraphyImageUrl: {
    type: String,
    default: ''
  },
  calligraphySelection: {
    type: Object,
    default: null
  },
  toolCalls: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['video-play', 'video-pause', 'video-ended', 'calligraphy-option'])

const contentParts = computed(() => {
  const parts = []
  const urlPattern = /https?:\/\/[^\s]+/g
  let lastIndex = 0

  for (const match of props.content.matchAll(urlPattern)) {
    if (match.index > lastIndex) {
      parts.push({ type: 'text', text: props.content.slice(lastIndex, match.index) })
    }
    parts.push({ type: 'link', text: match[0] })
    lastIndex = match.index + match[0].length
  }

  if (lastIndex < props.content.length) {
    parts.push({ type: 'text', text: props.content.slice(lastIndex) })
  }

  return parts.length ? parts : [{ type: 'text', text: props.content }]
})

const absoluteCalligraphyUrl = computed(() => {
  if (!props.calligraphyImageUrl) return ''
  if (/^https?:\/\//.test(props.calligraphyImageUrl)) {
    return props.calligraphyImageUrl
  }
  return `${API_BASE_URL}${props.calligraphyImageUrl}`
})

const normalizedToolCalls = computed(() => {
  return (props.toolCalls || []).map((tool) => {
    const status = tool.status || 'planned'
    return {
      name: tool.tool_name || tool.toolName || 'tool',
      stepId: tool.step_id || tool.stepId || '',
      agentName: tool.agent_display_name || tool.agentDisplayName || tool.agent_name || tool.agentName || '领域 Agent',
      displayName: tool.tool_display_name || tool.toolDisplayName || tool.tool_name || tool.toolName || '工具',
      status,
      statusText: formatToolStatus(status),
      summary: tool.thought_summary || tool.thoughtSummary || tool.goal || tool.reason || '',
      detail: tool.error || tool.content || '',
    }
  })
})

const completedToolCount = computed(() => {
  return normalizedToolCalls.value.filter((tool) => ['success', 'skipped', 'error', 'needs_input'].includes(tool.status)).length
})

function formatToolStatus(status) {
  const labels = {
    planned: '计划中',
    success: '已完成',
    needs_input: '待补充',
    skipped: '已跳过',
    error: '调用失败',
  }
  return labels[status] || status || '计划中'
}

const {
  styleOptions,
  activeStyle,
  activeAuthor,
  authorOptions,
  hasSelection,
  handleStyleOption,
  handleAuthorOption,
} = useCalligraphySelection(
  computed(() => props.calligraphySelection),
  (option) => emit('calligraphy-option', option)
)

</script>
