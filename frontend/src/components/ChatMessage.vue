<template>
  <div class="message-row" :class="role">
    <div v-if="role === 'assistant'" class="message-avatar" aria-hidden="true">
      <svg viewBox="0 0 24 24">
        <path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v11a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5v-11Z" />
        <path d="M8 9h8M8 12h8M8 15h5" />
      </svg>
    </div>
    <div class="message-bubble">
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
      <div v-if="calligraphyImageUrl" class="calligraphy-result">
        <img :src="absoluteCalligraphyUrl" alt="书法作品" />
      </div>
      <div v-if="toolCalls && toolCalls.length" class="tool-trace">
        <div
          v-for="(tool, index) in toolCalls"
          :key="`${tool.tool_name || tool.toolName}-${index}`"
          class="tool-trace-item"
        >
          <span>{{ tool.tool_name || tool.toolName }}</span>
          <small>{{ tool.status || tool.reason || 'planned' }}</small>
        </div>
      </div>
      <div v-if="videos && videos.length" class="video-list">
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
  toolCalls: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['video-play', 'video-pause', 'video-ended'])

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
</script>
