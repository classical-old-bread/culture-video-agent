import { ref } from 'vue'
import { synthesizeSpeech } from '../api/chat'

const SPEECH_SEGMENT_PAUSE_MS = 20
const SPEECH_CLOUD_TIMEOUT_MS = 12000
const SPEECH_SEGMENT_TARGET_SENTENCES = 4
const SPEECH_SEGMENT_MAX_SENTENCES = 5
const SPEECH_SEGMENT_MAX_LENGTH = 420
const SPEECH_SEGMENT_READY_LENGTH = 300

function normalizeSpeechText(text) {
  return text
    .replace(/[#*_`~>|]/g, '')
    .replace(/\r/g, '\n')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function extractSpeechSentences(text, { includeTrailing = false } = {}) {
  const normalized = normalizeSpeechText(text)
  const sentences = []
  let current = ''

  for (const char of normalized) {
    current += char
    if ('。！？；;\n'.includes(char)) {
      const sentence = current.trim()
      if (sentence) sentences.push(sentence)
      current = ''
    }
  }

  const rest = current.trim()
  if (includeTrailing && rest) {
    sentences.push(rest)
    return { sentences, rest: '' }
  }

  return { sentences, rest }
}

function splitLongSpeechSentence(sentence) {
  const normalized = sentence.trim()
  if (!normalized) return []
  if (normalized.length <= SPEECH_SEGMENT_MAX_LENGTH) return [normalized]

  const chunks = []
  let rest = normalized

  while (rest.length > SPEECH_SEGMENT_MAX_LENGTH) {
    const searchArea = rest.slice(0, SPEECH_SEGMENT_MAX_LENGTH)
    const softBreakIndex = Math.max(
      searchArea.lastIndexOf('，'),
      searchArea.lastIndexOf('、'),
      searchArea.lastIndexOf('；'),
      searchArea.lastIndexOf(';'),
      searchArea.lastIndexOf(' '),
    )
    const splitIndex = softBreakIndex >= 80 ? softBreakIndex + 1 : SPEECH_SEGMENT_MAX_LENGTH
    chunks.push(rest.slice(0, splitIndex).trim())
    rest = rest.slice(splitIndex).trim()
  }

  if (rest) chunks.push(rest)
  return chunks
}

function buildSpeechSegments(sentences, { force = true } = {}) {
  const pending = sentences.flatMap(splitLongSpeechSentence)
  const segments = []
  let current = []
  let currentLength = 0

  while (pending.length) {
    const nextSentence = pending[0]
    const willExceedLength = current.length > 0 && currentLength + nextSentence.length > SPEECH_SEGMENT_MAX_LENGTH
    const reachedMaxSentences = current.length >= SPEECH_SEGMENT_MAX_SENTENCES

    if (willExceedLength || reachedMaxSentences) {
      segments.push(current.join(''))
      current = []
      currentLength = 0
      continue
    }

    current.push(pending.shift())
    currentLength += nextSentence.length

    if (current.length >= SPEECH_SEGMENT_TARGET_SENTENCES || currentLength >= SPEECH_SEGMENT_READY_LENGTH) {
      segments.push(current.join(''))
      current = []
      currentLength = 0
    }
  }

  if (force && current.length) {
    segments.push(current.join(''))
  }

  return { segments, remaining: current }
}

function prepareSpeechSegments(text) {
  const { sentences } = extractSpeechSentences(text, { includeTrailing: true })
  return buildSpeechSegments(sentences, { force: true }).segments.slice(0, 40)
}

export function useSpeechPlayback({ onSpeechIdle } = {}) {
  const isSpeaking = ref(false)
  const localMediaPlaying = ref(false)
  const speechRunId = ref(0)
  const currentAudioRef = ref(null)
  const currentAudioUrlRef = ref('')
  const speechQueue = ref([])
  const speechQueuePlaying = ref(false)
  const speechPrefetch = ref(null)
  const speechPrefetchController = ref(null)
  const speechPrefetchPromise = ref(null)
  const streamingSpeechBuffer = ref('')
  const streamingSpeechSentences = ref([])

  function stopCurrentAudio() {
    speechRunId.value += 1
    speechQueue.value = []
    speechQueuePlaying.value = false
    speechPrefetch.value = null
    speechPrefetchPromise.value = null
    streamingSpeechBuffer.value = ''
    streamingSpeechSentences.value = []

    if (speechPrefetchController.value) {
      speechPrefetchController.value.abort()
      speechPrefetchController.value = null
    }

    if (currentAudioRef.value) {
      currentAudioRef.value.pause()
      currentAudioRef.value.src = ''
      currentAudioRef.value = null
    }

    if (currentAudioUrlRef.value) {
      URL.revokeObjectURL(currentAudioUrlRef.value)
      currentAudioUrlRef.value = ''
    }

    if (window.speechSynthesis) {
      window.speechSynthesis.cancel()
    }

    isSpeaking.value = false
  }

  function stopLocalMedia() {
    localMediaPlaying.value = false
    window.dispatchEvent(new CustomEvent('local-media-stop'))
  }

  function handleLocalMediaPlay() {
    localMediaPlaying.value = true
    stopCurrentAudio()
  }

  function handleLocalMediaStop() {
    localMediaPlaying.value = false
  }

  async function speakText(text) {
    if (!text) return
    stopCurrentAudio()
    queueSpeechSegments(prepareSpeechSegments(text))
  }

  function queueSpeechSegments(segments) {
    const validSegments = segments.map((segment) => segment.trim()).filter(Boolean)
    if (!validSegments.length) return

    speechQueue.value.push(...validSegments)
    if (speechQueuePlaying.value) {
      prefetchNextSpeechSegment()
    }
    playNextSpeechSegment()
  }

  async function requestSpeechBlob(segment, currentRunId, controllerRef = null) {
    const ttsController = new AbortController()
    if (controllerRef) {
      controllerRef.value = ttsController
    }

    const timeoutId = window.setTimeout(() => {
      ttsController.abort()
    }, SPEECH_CLOUD_TIMEOUT_MS)

    try {
      const audioBlob = await synthesizeSpeech(segment.slice(0, 500), {
        signal: ttsController.signal,
      })
      if (currentRunId !== speechRunId.value) return null
      return audioBlob
    } finally {
      window.clearTimeout(timeoutId)
      if (controllerRef?.value === ttsController) {
        controllerRef.value = null
      }
    }
  }

  function prefetchNextSpeechSegment(currentRunId = speechRunId.value) {
    if (speechPrefetch.value || speechPrefetchController.value || !speechQueue.value.length) return

    const nextSegment = speechQueue.value[0]
    const prefetchPromise = requestSpeechBlob(nextSegment, currentRunId, speechPrefetchController)
      .then((audioBlob) => {
        if (!audioBlob || currentRunId !== speechRunId.value) return null
        if (speechQueue.value[0] === nextSegment) {
          speechPrefetch.value = {
            text: nextSegment,
            audioBlob,
            promise: null,
          }
        }
        return audioBlob
      })
      .catch(() => {
        if (currentRunId === speechRunId.value && speechQueue.value[0] === nextSegment) {
          speechPrefetch.value = {
            text: nextSegment,
            audioBlob: null,
            promise: null,
            failed: true,
          }
        }
        return null
      })
      .finally(() => {
        if (speechPrefetchPromise.value === prefetchPromise) {
          speechPrefetchPromise.value = null
        }
      })

    speechPrefetchPromise.value = prefetchPromise
    speechPrefetch.value = {
      text: nextSegment,
      audioBlob: null,
      promise: prefetchPromise,
    }
  }

  function finishSpeechSegment(currentRunId, audioUrl = '') {
    if (currentRunId !== speechRunId.value) return

    if (audioUrl) {
      URL.revokeObjectURL(audioUrl)
    }

    currentAudioRef.value = null
    currentAudioUrlRef.value = ''
    speechQueuePlaying.value = false

    if (!speechQueue.value.length) {
      isSpeaking.value = false
      onSpeechIdle?.()
      return
    }

    isSpeaking.value = true
    prefetchNextSpeechSegment(currentRunId)
    window.setTimeout(playNextSpeechSegment, SPEECH_SEGMENT_PAUSE_MS)
  }

  async function playNextSpeechSegment() {
    if (speechQueuePlaying.value || !speechQueue.value.length) return

    const currentRunId = speechRunId.value
    const segment = speechQueue.value.shift()
    speechQueuePlaying.value = true
    isSpeaking.value = true

    try {
      let audioBlob
      if (speechPrefetch.value?.text === segment) {
        const prefetched = speechPrefetch.value
        speechPrefetch.value = null
        audioBlob = prefetched.audioBlob || await prefetched.promise
        if (prefetched.failed || !audioBlob) {
          throw new Error('Prefetched speech failed')
        }
      } else {
        speechPrefetch.value = null
        audioBlob = await requestSpeechBlob(segment, currentRunId)
      }

      if (!audioBlob || currentRunId !== speechRunId.value) return

      const audioUrl = URL.createObjectURL(audioBlob)
      const audio = new Audio(audioUrl)
      currentAudioRef.value = audio
      currentAudioUrlRef.value = audioUrl

      audio.onended = () => {
        finishSpeechSegment(currentRunId, audioUrl)
      }

      audio.onerror = () => {
        finishSpeechSegment(currentRunId, audioUrl)
      }

      await audio.play()
      prefetchNextSpeechSegment(currentRunId)
    } catch {
      if (currentRunId !== speechRunId.value) return

      speechQueuePlaying.value = false
      if (!speechQueue.value.length) {
        isSpeaking.value = false
        onSpeechIdle?.()
        return
      }

      isSpeaking.value = true
      prefetchNextSpeechSegment(currentRunId)
      window.setTimeout(playNextSpeechSegment, SPEECH_SEGMENT_PAUSE_MS)
    }
  }

  function drainStreamingSpeechSegments({ force = false } = {}) {
    if (!streamingSpeechSentences.value.length) return

    const { segments, remaining } = buildSpeechSegments(streamingSpeechSentences.value, { force })
    streamingSpeechSentences.value = remaining
    queueSpeechSegments(segments)
  }

  function queueStreamingSpeech(text, { flush = false } = {}) {
    streamingSpeechBuffer.value += text

    const { sentences, rest } = extractSpeechSentences(streamingSpeechBuffer.value, {
      includeTrailing: flush,
    })

    streamingSpeechBuffer.value = flush ? '' : rest
    if (sentences.length) {
      streamingSpeechSentences.value.push(...sentences)
    }

    drainStreamingSpeechSegments({ force: flush })
  }

  return {
    isSpeaking,
    localMediaPlaying,
    speechQueuePlaying,
    stopCurrentAudio,
    stopLocalMedia,
    handleLocalMediaPlay,
    handleLocalMediaStop,
    speakText,
    queueStreamingSpeech,
  }
}
