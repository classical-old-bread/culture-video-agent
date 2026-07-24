import { ref } from 'vue'
import { compactRepeatedVoiceText, createCloudRecognition } from './useCloudRecognition'

const RADIO_VOLUME_THRESHOLD = 0.004
const RADIO_SILENCE_MS = 3000
const RADIO_TEXT_IDLE_MS = 1600
const RADIO_DUPLICATE_IGNORE_MS = 9000
const RADIO_ASR_RESTART_MIN_MS = 500
const RADIO_ASR_RESTART_MAX_MS = 15000
const RADIO_ASR_ERROR_MESSAGE_INTERVAL_MS = 12000

function isFatalAsrError(detail = '') {
  return /未配置|未开通|没有流式 ASR 权限|没有流式ASR权限|resource not granted|requested resource not granted|code['":=\s]+403|连接被拒绝|HTTP 400|麦克风权限|NotAllowed/i.test(detail)
}

export function useRadioMode({
  input,
  loading,
  radioModeActive,
  recognitionRef,
  isListening,
  pendingVoiceText,
  sendMessage,
  pushSystemMessage,
  stopCurrentRecognition,
  stopLocalMedia,
  stopCurrentAudio,
  isAssistantOutputActive,
  isInterruptCommand,
  shouldInterruptFromTranscript,
  normalizeVoiceText,
  onInterruptCommand,
}) {
  const radioHasVoice = ref(false)
  const radioSubmitting = ref(false)
  const radioRecognitionStarting = ref(false)
  const radioAsrRestartDelay = ref(RADIO_ASR_RESTART_MIN_MS)
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

  function resetRadioPendingState() {
    radioSubmitting.value = false
    pendingVoiceText.value = ''
    input.value = ''
    radioHasVoice.value = false
    radioLastVoiceAt.value = 0
    window.clearTimeout(radioSubmitTimerRef.value)
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
          onInterruptCommand()
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
      onInterruptCommand()
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

  function beforeChatSend() {
    if (!radioModeActive.value) return
    window.clearTimeout(radioSubmitTimerRef.value)
    stopCurrentRecognition({ abort: true })
  }

  function afterChatSend() {
    if (!radioModeActive.value) return
    radioSubmitting.value = false
    scheduleRadioRecognitionRestart()
  }

  return {
    radioHasVoice,
    radioSubmitting,
    toggleRadioMode,
    startRadioMode,
    stopRadioMode,
    scheduleRadioRecognitionRestart,
    resetRadioPendingState,
    beforeChatSend,
    afterChatSend,
  }
}
