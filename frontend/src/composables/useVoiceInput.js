import { compactRepeatedVoiceText, createCloudRecognition } from './useCloudRecognition'

const VOICE_HOTKEY_CODES = new Set(['F8', 'F9', 'MediaRecord'])

export function useVoiceInput({
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
  onInterruptCommand,
}) {
  let voiceIsPressed = false
  let voiceStopRequested = false

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
        // Some browsers may reject pointer capture for synthetic events.
      }
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      pushSystemMessage('当前浏览器无法读取麦克风，请确认浏览器和权限设置。')
      return
    }

    stopLocalMedia()
    stopCurrentAudio()

    voiceIsPressed = true
    voiceStopRequested = false
    pendingVoiceText.value = ''

    try {
      const recognition = await createCloudRecognition({
        onStart() {
          isListening.value = true
        },
        onText(transcript) {
          if (!transcript) return
          if (shouldInterruptFromTranscript(transcript)) {
            voiceIsPressed = false
            voiceStopRequested = false
            onInterruptCommand()
            return
          }

          pendingVoiceText.value = transcript
          input.value = transcript
        },
        async onEnd() {
          isListening.value = false
          recognitionRef.value = null

          const text = compactRepeatedVoiceText(pendingVoiceText.value).trim()
          const shouldSend = voiceStopRequested && text

          voiceIsPressed = false
          voiceStopRequested = false

          if (shouldSend) {
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
      voiceIsPressed = false
      pushSystemMessage(error?.name === 'NotAllowedError'
        ? '浏览器没有获得麦克风权限，请允许麦克风后再试。'
        : '火山语音识别启动失败，请稍后重试。')
    }
  }

  function finishVoiceInput() {
    if (!voiceIsPressed && !isListening.value) return

    voiceIsPressed = false
    voiceStopRequested = true

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

  return {
    startVoiceInput,
    finishVoiceInput,
    stopCurrentRecognition,
    handleGlobalVoiceKeyDown,
    handleGlobalVoiceKeyUp,
  }
}
