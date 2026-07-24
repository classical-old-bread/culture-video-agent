import { ASR_WS_URL } from '../api/chat'

const ASR_SAMPLE_RATE = 16000
const ASR_PROCESSOR_BUFFER_SIZE = 4096

export function compactRepeatedVoiceText(text) {
  const normalized = text.trim()
  if (!normalized) return ''

  const clauses = normalized
    .split(/[，。！？!?,.；;：:、\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)

  if (clauses.length >= 3 && clauses.every((item) => item === clauses[0]) && clauses[0].length <= 12) {
    return clauses[0]
  }

  const compact = normalized.replace(/[，。！？!?,.；;：:、\s]+/g, '')
  for (let unitLength = 1; unitLength <= 12; unitLength += 1) {
    if (compact.length < unitLength * 3 || compact.length % unitLength !== 0) continue
    const unit = compact.slice(0, unitLength)
    if (unit.repeat(compact.length / unitLength) === compact) {
      return unit
    }
  }

  return normalized
}

function downsampleTo16BitPcm(input, inputSampleRate) {
  const sampleRateRatio = inputSampleRate / ASR_SAMPLE_RATE
  const outputLength = Math.floor(input.length / sampleRateRatio)
  const output = new Int16Array(outputLength)
  let outputIndex = 0
  let inputIndex = 0

  while (outputIndex < outputLength) {
    const nextInputIndex = Math.floor((outputIndex + 1) * sampleRateRatio)
    let sum = 0
    let count = 0

    for (let index = inputIndex; index < nextInputIndex && index < input.length; index += 1) {
      sum += input[index]
      count += 1
    }

    const sample = Math.max(-1, Math.min(1, sum / Math.max(1, count)))
    output[outputIndex] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
    outputIndex += 1
    inputIndex = nextInputIndex
  }

  return output.buffer
}

export async function createCloudRecognition({ onText, onStart, onEnd, onError, stream: existingStream = null }) {
  const stream = existingStream || await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  })
  const ownsStream = !existingStream
  const AudioContext = window.AudioContext || window.webkitAudioContext
  const audioContext = new AudioContext()
  const source = audioContext.createMediaStreamSource(stream)
  const processor = audioContext.createScriptProcessor(ASR_PROCESSOR_BUFFER_SIZE, 1, 1)
  const socket = new WebSocket(ASR_WS_URL)
  socket.binaryType = 'arraybuffer'

  let stopped = false
  let socketReady = false
  let audioStopped = false

  function stopAudioCapture() {
    if (audioStopped) return
    audioStopped = true
    socketReady = false
    try {
      source.disconnect()
    } catch {
      // Already disconnected.
    }
    try {
      processor.disconnect()
    } catch {
      // Already disconnected.
    }
    if (ownsStream) {
      stream.getTracks().forEach((track) => track.stop())
    }
    audioContext.close()
  }

  function cleanup() {
    if (stopped) return
    stopped = true
    stopAudioCapture()
    onEnd?.()
  }

  processor.onaudioprocess = (event) => {
    if (!socketReady || audioStopped || stopped || socket.readyState !== WebSocket.OPEN) return
    const input = event.inputBuffer.getChannelData(0)
    const pcm = downsampleTo16BitPcm(input, audioContext.sampleRate)
    if (pcm.byteLength) {
      socket.send(pcm)
    }
  }

  socket.onopen = () => {
    socketReady = true
    source.connect(processor)
    processor.connect(audioContext.destination)
    onStart?.()
  }

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.event === 'result' && data.text) {
        onText?.(compactRepeatedVoiceText(data.text))
      } else if (data.event === 'error') {
        onError?.(data.detail || '火山语音识别失败。')
      } else if (data.event === 'done') {
        cleanup()
      }
    } catch {
      // Ignore malformed ASR messages.
    }
  }

  socket.onerror = () => {
    onError?.('火山语音识别连接失败。')
    cleanup()
  }

  socket.onclose = () => {
    cleanup()
  }

  return {
    stop() {
      if (stopped) return
      stopAudioCapture()
      try {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ event: 'end' }))
        } else {
          socket.close()
          cleanup()
        }
      } catch {
        cleanup()
      }
    },
    abort() {
      if (stopped) return
      try {
        socket.close()
      } catch {}
      cleanup()
    },
  }
}
