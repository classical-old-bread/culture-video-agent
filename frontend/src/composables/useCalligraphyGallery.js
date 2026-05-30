import { computed, ref } from 'vue'
import { API_BASE_URL, fetchCalligraphyGallery } from '../api/chat'

export function useCalligraphyGallery() {
  const activeView = ref('chat')
  const galleryItems = ref([])
  const galleryLoading = ref(false)
  const galleryLoaded = ref(false)

  const galleryRows = computed(() => {
    const rowCount = 4
    return Array.from({ length: rowCount }, (_, rowIndex) => {
      const rowItems = galleryItems.value.filter((_, index) => index % rowCount === rowIndex)
      return [...rowItems, ...rowItems]
    }).filter((row) => row.length)
  })

  function absoluteGalleryImageUrl(imageUrl) {
    if (!imageUrl) return ''
    if (/^https?:\/\//.test(imageUrl)) return imageUrl
    return `${API_BASE_URL}${imageUrl}`
  }

  async function loadCalligraphyGallery() {
    if (galleryLoaded.value || galleryLoading.value) return

    galleryLoading.value = true
    try {
      galleryItems.value = await fetchCalligraphyGallery()
      galleryLoaded.value = true
    } catch {
      galleryItems.value = []
    } finally {
      galleryLoading.value = false
    }
  }

  function selectNavItem(item) {
    if (item.muted) return
    activeView.value = item.view
    if (item.view === 'knowledge') {
      loadCalligraphyGallery()
    }
  }

  return {
    activeView,
    galleryItems,
    galleryLoading,
    galleryRows,
    absoluteGalleryImageUrl,
    selectNavItem,
  }
}
