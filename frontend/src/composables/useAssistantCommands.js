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

export function useAssistantCommands({ isAssistantOutputActive }) {
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

  return {
    isInterruptCommand,
    shouldInterruptFromTranscript,
    normalizeVoiceText,
  }
}
