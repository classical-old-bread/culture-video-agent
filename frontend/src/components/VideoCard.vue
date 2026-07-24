<template>
  <div class="video-card">
    <div class="video-meta">
      <div>
        <div class="video-kicker">{{ isAudio ? '本地音频' : '本地视频' }}</div>
        <div class="video-name">{{ video.video_name }}</div>
        <div v-if="video.category" class="video-id">{{ video.category }}</div>
      </div>
      <div class="video-id">ID {{ video.id }}</div>
    </div>

    <div class="video-frame" :class="{ 'audio-frame': isAudio }">
      <audio
        v-if="isAudio"
        ref="mediaRef"
        class="video-player audio-player"
        controls
        preload="metadata"
        :autoplay="autoPlay"
        :src="videoUrl"
        @error="handleVideoError"
        @play="handleMediaPlay"
        @pause="handleMediaPause"
        @ended="handleMediaEnded"
      />
      <video
        v-else
        ref="mediaRef"
        class="video-player"
        controls
        preload="metadata"
        playsinline
        :autoplay="autoPlay"
        :src="videoUrl"
        @error="handleVideoError"
        @play="handleMediaPlay"
        @pause="handleMediaPause"
        @ended="handleMediaEnded"
      />
    </div>

    <p v-if="loadError" class="video-error">
      媒体文件不存在或数据库中的文件路径不可用，请检查 media_resources.file_path。
    </p>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { API_BASE_URL } from '../api/chat'

const props = defineProps({
  video: {
    type: Object,
    required: true
  },
  autoPlay: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['play', 'pause', 'ended'])

const loadError = ref(false)
const mediaRef = ref(null)
const playerId = `local-media-${Date.now()}-${Math.random().toString(16).slice(2)}`
const videoUrl = computed(() => `${API_BASE_URL}/api/video/${props.video.id}`)
const isAudio = computed(() => {
  const mediaType = props.video.media_type || ''
  const mediaKind = props.video.media_kind || ''
  const filePath = props.video.file_path || ''
  if (mediaKind === 'video' || mediaType.startsWith('video/') || /\.(mp4|m4v|mov|webm)$/i.test(filePath)) {
    return false
  }
  return mediaKind === 'audio' || mediaType.startsWith('audio/') || /\.(mp3|wav|m4a|aac|ogg|flac)$/i.test(filePath)
})

function handleVideoError() {
  loadError.value = true
}

function pauseMedia({ reset = false } = {}) {
  if (!mediaRef.value) return
  mediaRef.value.pause()
  if (reset) {
    try {
      mediaRef.value.currentTime = 0
    } catch {
    }
  }
}

function handleMediaPlay() {
  window.dispatchEvent(new CustomEvent('local-media-play', { detail: { playerId } }))
  emit('play')
}

function handleMediaPause() {
  emit('pause')
}

function handleMediaEnded() {
  emit('ended')
}

function handlePeerMediaPlay(event) {
  if (event.detail?.playerId !== playerId) {
    pauseMedia()
  }
}

function handleLocalMediaStop() {
  pauseMedia()
}

async function tryAutoPlay() {
  if (!props.autoPlay || !mediaRef.value) return
  await nextTick()
  try {
    mediaRef.value.muted = false
    await mediaRef.value.play()
  } catch {
    // Autoplay is best-effort because browsers may require a direct user gesture.
  }
}

onMounted(() => {
  window.addEventListener('local-media-play', handlePeerMediaPlay)
  window.addEventListener('local-media-stop', handleLocalMediaStop)
  tryAutoPlay()
})

onBeforeUnmount(() => {
  window.removeEventListener('local-media-play', handlePeerMediaPlay)
  window.removeEventListener('local-media-stop', handleLocalMediaStop)
})

watch(() => props.autoPlay, tryAutoPlay)
</script>
