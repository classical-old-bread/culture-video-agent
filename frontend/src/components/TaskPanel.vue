<template>
  <aside class="task-panel" aria-label="任务结果面板">
    <div class="task-panel-header">
      <div>
        <span class="panel-kicker">Workspace</span>
        <h2>{{ panelTitle }}</h2>
      </div>
      <span class="panel-status" :class="{ active: loading }">
        <span aria-hidden="true"></span>
        {{ loading ? '处理中' : panelStatus }}
      </span>
    </div>

    <div v-if="mode === 'empty'" class="task-empty">
      <strong>等待任务</strong>
      <p>从左侧输入文化问答、书法生成、短剧脚本或媒体检索需求，结果会自动归类到这里。</p>
    </div>

    <div v-else class="task-stack">
      <section v-if="shortVideoProject" class="task-section video-project">
        <div class="section-heading">
          <span>{{ shortVideoProject.title }}</span>
          <button type="button" class="panel-copy-button" @click="copyProjectPrompts">复制全部提示词</button>
        </div>

        <div class="project-meta-grid">
          <div>
            <span>主题</span>
            <strong>{{ shortVideoProject.topic }}</strong>
          </div>
          <div>
            <span>受众</span>
            <strong>{{ shortVideoProject.audience }}</strong>
          </div>
        </div>

        <div class="project-note">
          <span>寓意</span>
          <p>{{ shortVideoProject.moral }}</p>
        </div>

        <div class="project-note">
          <span>统一画风</span>
          <p>{{ shortVideoProject.visual_style }}</p>
        </div>
      </section>

      <section v-if="shortVideoProject" class="task-section">
        <div class="section-heading">
          <span>五镜头分镜</span>
          <small>{{ shortVideoProject.shots?.length || 0 }} 个镜头</small>
        </div>

        <div class="shot-card-list">
          <article
            v-for="shot in shortVideoProject.shots"
            :key="shot.shot"
            class="shot-card"
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
            <div class="prompt-box">
              <div>
                <span>AI 视频提示词</span>
                <button type="button" @click="copyText(shot.video_prompt)">复制</button>
              </div>
              <p>{{ shot.video_prompt }}</p>
            </div>
          </article>
        </div>
      </section>

      <section v-if="shortVideoProject?.negative_prompt" class="task-section">
        <div class="section-heading">
          <span>负面提示词</span>
          <button type="button" class="panel-copy-button" @click="copyText(shortVideoProject.negative_prompt)">复制</button>
        </div>
        <p class="task-note">{{ shortVideoProject.negative_prompt }}</p>
      </section>

      <section v-if="hasSelection" class="task-section">
        <div class="section-heading">
          <span>书法选项</span>
          <small>{{ selectionCount }} 个选项</small>
        </div>

        <div v-if="styleOptions.length" class="choice-group">
          <span class="choice-label">选择书法风格</span>
          <div class="panel-option-grid">
            <button
              v-for="option in styleOptions"
              :key="`panel-style-${option.value}`"
              type="button"
              class="panel-option"
              :class="{ active: option.value === activeStyle }"
              @click="handleStyleOption(option)"
            >
              {{ option.label }}
            </button>
          </div>
        </div>

        <div v-if="authorOptions.length" class="choice-group">
          <span class="choice-label">选择书法作者</span>
          <div class="panel-option-grid">
            <button
              v-for="option in authorOptions"
              :key="`panel-author-${option.style || activeStyle}-${option.value}`"
              type="button"
              class="panel-option"
              :class="{ active: option.value === activeAuthor }"
              @click="handleAuthorOption(option)"
            >
              {{ option.label }}
            </button>
          </div>
        </div>
      </section>

      <section v-if="message?.calligraphyImageUrl" class="task-section">
        <div class="section-heading">
          <span>书法作品</span>
          <a :href="absoluteCalligraphyUrl" target="_blank" rel="noopener noreferrer">打开原图</a>
        </div>
        <div class="calligraphy-preview">
          <img :src="absoluteCalligraphyUrl" alt="生成的书法作品" />
        </div>
        <p v-if="message.calligraphyMissingChars?.length" class="task-note">
          字库缺少：{{ message.calligraphyMissingChars.slice(0, 24).join('、') }}
        </p>
      </section>

      <section v-if="message?.sources?.length" class="task-section">
        <div class="section-heading">
          <span>参考来源</span>
          <small>{{ message.sources.length }} 条</small>
        </div>
        <div class="source-list">
          <a
            v-for="(source, index) in normalizedSources"
            :key="`${source.title}-${index}`"
            class="source-item"
            :href="source.url || undefined"
            :target="source.url ? '_blank' : undefined"
            rel="noopener noreferrer"
          >
            <strong>{{ source.title }}</strong>
            <p>{{ source.snippet }}</p>
          </a>
        </div>
      </section>

    </div>
  </aside>
</template>

<script setup>
import { computed } from 'vue'
import { API_BASE_URL } from '../api/chat'
import { useCalligraphySelection } from '../composables/useCalligraphySelection'

const props = defineProps({
  message: {
    type: Object,
    default: null
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'video-play',
  'video-pause',
  'video-ended',
  'calligraphy-option'
])

const shortVideoProject = computed(() => props.message?.shortVideoProject || null)

const mode = computed(() => {
  if (!props.message) return 'empty'
  if (shortVideoProject.value) return 'short_video'
  if (hasSelection.value) return 'selection'
  if (props.message.calligraphyImageUrl) return 'calligraphy'
  if (props.message.sources?.length) return 'sources'
  return 'empty'
})

const panelTitle = computed(() => {
  const titles = {
    empty: '任务面板',
    short_video: '短剧工作区',
    selection: '书法选择',
    calligraphy: '书法生成',
    media: '媒体检索',
    sources: '知识来源',
  }
  return titles[mode.value] || '任务面板'
})

const panelStatus = computed(() => {
  if (!props.message) return '空闲'
  if (props.message.responseType) return props.message.responseType
  return '已更新'
})

const absoluteCalligraphyUrl = computed(() => {
  const url = props.message?.calligraphyImageUrl || ''
  if (!url) return ''
  return /^https?:\/\//.test(url) ? url : `${API_BASE_URL}${url}`
})

const {
  styleOptions,
  activeStyle,
  activeAuthor,
  authorOptions,
  hasSelection,
  selectionCount,
  handleStyleOption,
  handleAuthorOption,
} = useCalligraphySelection(
  computed(() => props.message?.calligraphySelection),
  (option) => emit('calligraphy-option', option)
)

const normalizedSources = computed(() => {
  return (props.message?.sources || []).map((source) => ({
    title: source.title || source.source || source.url || '未命名来源',
    url: source.url || '',
    snippet: source.snippet || source.content || ''
  }))
})

function copyProjectPrompts() {
  if (!shortVideoProject.value) return
  const text = shortVideoProject.value.shots
    .map((shot) => `镜头${shot.shot}：${shot.video_prompt}`)
    .join('\n\n')
  copyText(`${text}\n\n负面提示词：${shortVideoProject.value.negative_prompt}`)
}

async function copyText(text) {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // Clipboard may be unavailable on non-secure origins.
  }
}

</script>
