<template>
  <div class="global-search" :class="{ 'is-focused': isFocused }">
    <el-input
      v-model="searchKeyword"
      :placeholder="placeholder"
      clearable
      @focus="handleFocus"
      @blur="handleBlur"
      @keyup.enter="handleSearch"
      @clear="handleClear"
    >
      <template #prefix>
        <el-icon><Search /></el-icon>
      </template>
      <template #suffix>
        <kbd v-if="!isFocused" class="global-search__shortcut">
          {{ hotkey }}
        </kbd>
      </template>
    </el-input>
    
    <el-dropdown
      v-if="isFocused && (suggestions.length || recentSearches.length)"
      trigger="manual"
      :visible="showDropdown"
      placement="bottom-start"
      :teleported="false"
      popper-class="app-tooltip-popper"
    >
      <div />
      <template #dropdown>
        <el-dropdown-menu class="global-search__dropdown">
          <el-dropdown-item v-if="recentSearches.length" disabled divided>
            <div class="global-search__section-title">最近搜索</div>
          </el-dropdown-item>
          <el-dropdown-item
            v-for="item in recentSearches"
            :key="item"
            @click="handleRecentClick(item)"
          >
            <el-icon class="el-icon--left"><Clock /></el-icon>
            {{ item }}
          </el-dropdown-item>
          
          <el-dropdown-item v-if="suggestions.length" divided>
            <div class="global-search__section-title">搜索建议</div>
          </el-dropdown-item>
          <el-dropdown-item
            v-for="suggestion in suggestions"
            :key="suggestion.id"
            @click="handleSuggestionClick(suggestion)"
          >
            <el-icon class="el-icon--left">
              <component :is="getSuggestionIcon(suggestion.type)" />
            </el-icon>
            <div class="global-search__suggestion-content">
              <div class="global-search__suggestion-title">{{ suggestion.title }}</div>
              <div v-if="suggestion.subtitle" class="global-search__suggestion-subtitle">
                {{ suggestion.subtitle }}
              </div>
            </div>
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Search, Clock, Document, Folder, Setting, User } from '@element-plus/icons-vue'

const props = defineProps({
  placeholder: {
    type: String,
    default: '搜索...'
  },
  hotkey: {
    type: String,
    default: 'Ctrl+K'
  },
  suggestions: {
    type: Array,
    default: () => []
  },
  recentSearches: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['search', 'suggestion-click', 'recent-click', 'clear'])

const isFocused = ref(false)
const showDropdown = ref(false)
const searchKeyword = ref('')

function handleFocus() {
  isFocused.value = true
  showDropdown.value = true
}

function handleBlur() {
  setTimeout(() => {
    isFocused.value = false
    showDropdown.value = false
  }, 200)
}

function handleSearch() {
  if (searchKeyword.value) {
    emit('search', searchKeyword.value)
    showDropdown.value = false
  }
}

function handleClear() {
  emit('clear')
}

function handleRecentClick(keyword) {
  searchKeyword.value = keyword
  emit('recent-click', keyword)
  emit('search', keyword)
  showDropdown.value = false
}

function handleSuggestionClick(suggestion) {
  emit('suggestion-click', suggestion)
  showDropdown.value = false
}

function getSuggestionIcon(type) {
  const iconMap = {
    page: Document,
    folder: Folder,
    user: User,
    setting: Setting
  }
  return iconMap[type] || Document
}

// 全局快捷键
function handleKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault()
    document.querySelector('.global-search input')?.focus()
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.global-search {
  position: relative;
  width: 240px;
}

.global-search :deep(.el-input) {
  width: 100%;
}

.global-search :deep(.el-input__wrapper) {
  border-radius: var(--el-border-radius-base, 6px);
}

.global-search__shortcut {
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  font-size: 11px;
  font-family: system-ui;
  background: var(--el-fill-color-light, #f5f7fa);
  border: 1px solid var(--el-border-color, #e5e6eb);
  border-radius: 4px;
  color: var(--el-text-color-placeholder, #a0adbb);
}

.global-search__dropdown {
  min-width: 300px;
}

.global-search__section-title {
  padding: var(--spacing-xs) var(--spacing-sm);
  font-size: var(--el-font-size-small, 12px);
  color: var(--el-text-color-placeholder, #a0adbb);
}

.global-search__suggestion-content {
  flex: 1;
}

.global-search__suggestion-title {
  font-size: var(--el-font-size-base, 14px);
  color: var(--el-text-color-primary, #1d2129);
}

.global-search__suggestion-subtitle {
  font-size: var(--el-font-size-small, 12px);
  color: var(--el-text-color-secondary, #606266);
}

.global-search.is-focused :deep(.el-input__wrapper) {
  border-color: var(--yonyou-orange-600, #ea580c);
}
</style>
