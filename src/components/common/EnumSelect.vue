<template>
  <div
    ref="selectRef"
    :class="selectClasses"
    @click="toggleDropdown"
    @keydown="handleKeydown"
    tabindex="0"
  >
    <div class="enum-select__trigger">
      <span v-if="selectedLabel" class="enum-select__value">{{ selectedLabel }}</span>
      <span v-else class="enum-select__placeholder">{{ placeholder }}</span>
      <span class="enum-select__icons">
        <span
          v-if="clearable && modelValue && !disabled"
          class="enum-select__clear"
          @click.stop="clearValue"
        >
          <svg viewBox="0 0 24 24" width="14" height="14">
            <path fill="currentColor" d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
          </svg>
        </span>
        <span class="enum-select__arrow" :class="{ 'enum-select__arrow--open': isOpen }">
          <svg viewBox="0 0 24 24" width="16" height="16">
            <path fill="currentColor" d="M7 10l5 5 5-5z"/>
          </svg>
        </span>
      </span>
    </div>
    <transition name="enum-select-dropdown">
      <div v-show="isOpen" class="enum-select__dropdown">
        <div class="enum-select__search">
          <input
            ref="searchInput"
            v-model="searchQuery"
            type="text"
            class="enum-select__search-input"
            placeholder="搜索..."
            @click.stop
          />
        </div>
        <div v-if="loading" class="enum-select__loading">加载中...</div>
        <div v-else class="enum-select__options">
          <div
            v-for="option in filteredOptions"
            :key="option.code"
            :class="optionClasses(option)"
            @click.stop="selectOption(option)"
          >
            <span class="enum-select__option-label">{{ option.name }}</span>
            <span v-if="isSelected(option)" class="enum-select__check">
              <svg viewBox="0 0 24 24" width="16" height="16">
                <path fill="currentColor" d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
              </svg>
            </span>
          </div>
          <div v-if="filteredOptions.length === 0 && !loading" class="enum-select__empty">
            无匹配选项
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import EnumService from '@/services/enumService'

const props = defineProps({
  enumType: {
    type: String,
    required: true
  },
  modelValue: {
    type: String,
    default: ''
  },
  enumFilter: {
    type: Object,
    default: () => ({})
  },
  placeholder: {
    type: String,
    default: '请选择'
  },
  disabled: {
    type: Boolean,
    default: false
  },
  clearable: {
    type: Boolean,
    default: false
  },
  useHighSpeedEndpoint: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['update:modelValue'])

const selectRef = ref(null)
const searchInput = ref(null)
const isOpen = ref(false)
const searchQuery = ref('')
const options = ref([])
const loading = ref(false)

const selectClasses = computed(() => [
  'enum-select',
  {
    'enum-select--disabled': props.disabled,
    'enum-select--open': isOpen.value,
    'enum-select--has-value': props.modelValue
  }
])

const filteredOptions = computed(() => {
  if (!searchQuery.value) {
    return options.value
  }
  const query = searchQuery.value.toLowerCase()
  return options.value.filter(option =>
    option.name?.toLowerCase().includes(query) ||
    option.code?.toLowerCase().includes(query)
  )
})

const selectedLabel = computed(() => {
  const selected = options.value.find(opt => opt.code === props.modelValue)
  return selected?.name || ''
})

const isSelected = (option) => {
  return props.modelValue === option.code
}

const optionClasses = (option) => [
  'enum-select__option',
  {
    'enum-select__option--selected': isSelected(option)
  }
]

async function loadEnumValues() {
  if (!props.enumType) return

  loading.value = true
  try {
    const values = await EnumService.loadOptions(props.enumType, {
      cache: true,
      useHighSpeedEndpoint: props.useHighSpeedEndpoint,
      filter: props.enumFilter,
      throwError: false // 不抛出错误，由组件处理
    })

    // EnumService 返回统一格式 {value, label, code, name}
    // 转换为组件使用的格式 {code, name} 以保持向后兼容
    options.value = values.map(v => ({
      code: v.code || v.value,
      name: v.name || v.label
    }))

  } catch (e) {
    console.error('Failed to load enum values:', e)
    options.value = []
  } finally {
    loading.value = false
  }
}

const toggleDropdown = () => {
  if (props.disabled) return
  isOpen.value = !isOpen.value
  if (isOpen.value) {
    nextTick(() => {
      searchInput.value?.focus()
    })
  }
}

const selectOption = (option) => {
  emit('update:modelValue', option.code)
  isOpen.value = false
}

const clearValue = () => {
  emit('update:modelValue', '')
}

const handleKeydown = (event) => {
  if (props.disabled) return

  switch (event.key) {
    case 'Enter':
    case ' ':
      event.preventDefault()
      toggleDropdown()
      break
    case 'Escape':
      isOpen.value = false
      break
  }
}

const handleClickOutside = (event) => {
  if (selectRef.value && !selectRef.value.contains(event.target)) {
    isOpen.value = false
  }
}

watch(() => props.enumType, () => {
  loadEnumValues()
}, { immediate: true })

watch(() => props.enumFilter, () => {
  loadEnumValues()
}, { deep: true })

watch(isOpen, (newVal) => {
  if (!newVal) {
    searchQuery.value = ''
  }
})

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<style scoped>
.enum-select {
  position: relative;
  display: inline-block;
  width: 100%;
  font-family: var(--font-family);
}

.enum-select__trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  height: var(--input-height-md);
  padding: 0 var(--spacing-md);
  background: var(--color-bg-base);
  border: var(--border-width-thin) solid var(--color-border);
  border-radius: var(--radius-input);
  cursor: pointer;
  transition: var(--transition-normal);
}

.enum-select__trigger:hover {
  border-color: var(--color-primary);
}

.enum-select--open .enum-select__trigger {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.enum-select--disabled .enum-select__trigger {
  background: var(--color-bg-disabled);
  color: var(--color-text-disabled);
  cursor: not-allowed;
}

.enum-select--disabled .enum-select__trigger:hover {
  border-color: var(--color-border);
}

.enum-select__value {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text-primary);
}

.enum-select__placeholder {
  flex: 1;
  color: var(--color-text-placeholder);
}

.enum-select__icons {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin-left: var(--spacing-sm);
}

.enum-select__clear {
  display: flex;
  align-items: center;
  color: var(--color-text-tertiary);
  cursor: pointer;
  transition: color var(--transition-fast);
}

.enum-select__clear:hover {
  color: var(--color-text-primary);
}

.enum-select__arrow {
  display: flex;
  align-items: center;
  color: var(--color-text-tertiary);
  transition: transform var(--transition-normal);
}

.enum-select__arrow--open {
  transform: rotate(180deg);
}

.enum-select__dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin-top: var(--spacing-xs);
  background: var(--color-bg-container);
  border: var(--border-width-thin) solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  z-index: var(--z-index-dropdown);
  max-height: 300px;
  overflow-y: auto;
}

.enum-select__search {
  padding: var(--spacing-sm);
  border-bottom: var(--border-width-thin) solid var(--color-border-secondary);
  position: sticky;
  top: 0;
  background: var(--color-bg-container);
}

.enum-select__search-input {
  width: 100%;
  height: 32px;
  padding: 0 var(--spacing-sm);
  font-family: var(--font-family);
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  background: var(--color-bg-base);
  border: var(--border-width-thin) solid var(--color-border);
  border-radius: var(--radius-sm);
  outline: none;
}

.enum-select__search-input:focus {
  border-color: var(--color-primary);
}

.enum-select__loading {
  padding: var(--spacing-lg);
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

.enum-select__options {
  padding: var(--spacing-xs) 0;
}

.enum-select__option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.enum-select__option:hover {
  background: var(--color-bg-secondary);
}

.enum-select__option--selected {
  background: var(--color-selected);
  color: var(--color-primary);
}

.enum-select__option-label {
  flex: 1;
}

.enum-select__check {
  display: flex;
  align-items: center;
  margin-left: var(--spacing-sm);
}

.enum-select__empty {
  padding: var(--spacing-md);
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

.enum-select-dropdown-enter-active,
.enum-select-dropdown-leave-active {
  transition: opacity var(--transition-fast), transform var(--transition-fast);
}

.enum-select-dropdown-enter-from,
.enum-select-dropdown-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
