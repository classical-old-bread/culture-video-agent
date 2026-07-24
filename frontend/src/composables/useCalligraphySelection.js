import { computed, ref, watch } from 'vue'

export function useCalligraphySelection(selectionRef, emitOption) {
  const selectedStyle = ref('')
  const selectedAuthor = ref('')

  watch(
    selectionRef,
    (selection) => {
      selectedStyle.value = selection?.style || ''
      selectedAuthor.value = selection?.author || ''
    },
    { immediate: true }
  )

  const selectionOptions = computed(() => {
    const options = selectionRef.value?.options
    return Array.isArray(options) ? options : []
  })

  const styleGroups = computed(() => {
    const groups = selectionRef.value?.groups
    return Array.isArray(groups) ? groups : []
  })

  const styleOptions = computed(() => selectionOptions.value.filter((option) => option.type === 'style'))

  const activeStyle = computed(() => selectedStyle.value || selectionRef.value?.style || '')
  const activeAuthor = computed(() => selectedAuthor.value || selectionRef.value?.author || '')

  const authorOptions = computed(() => {
    const directAuthors = selectionOptions.value.filter((option) => option.type === 'author')
    if (directAuthors.length) return directAuthors
    if (!activeStyle.value) return []

    const group = styleGroups.value.find((item) => item.style === activeStyle.value)
    return (group?.authors || []).map((author) => ({
      type: 'author',
      label: author,
      value: author,
      style: activeStyle.value,
    }))
  })

  const hasSelection = computed(() => Boolean(styleOptions.value.length || authorOptions.value.length))
  const selectionCount = computed(() => styleOptions.value.length + authorOptions.value.length)

  function handleStyleOption(option) {
    const authors = option.authors || styleGroups.value.find((item) => item.style === option.value)?.authors || []
    if (authors.length) {
      selectedStyle.value = option.value
      selectedAuthor.value = ''
      return
    }
    emitOption(option)
  }

  function handleAuthorOption(option) {
    selectedAuthor.value = option.value
    emitOption(option)
  }

  return {
    selectedStyle,
    selectedAuthor,
    styleOptions,
    activeStyle,
    activeAuthor,
    authorOptions,
    hasSelection,
    selectionCount,
    handleStyleOption,
    handleAuthorOption,
  }
}
