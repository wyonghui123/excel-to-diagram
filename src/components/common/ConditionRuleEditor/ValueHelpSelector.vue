<template>
  <div class="value-help-selector" :class="{ 'value-help-selector--disabled': disabled }">
    <div class="selected-tags" @click="handleFocus">
      <template v-if="multiple">
        <span v-for="tag in selectedValues" :key="tag.id" class="value-tag">
          {{ tag.display_name }}
          <button class="tag-remove" @click.stop="removeTag(tag)">&times;</button>
        </span>
      </template>
      <template v-else>
        <span v-if="displayValue" class="value-tag single-tag">
          {{ displayValue }}
          <button v-if="!disabled" class="tag-remove" @click.stop="clearValue">&times;</button>
        </span>
      </template>
      <input
        ref="inputRef"
        v-model="searchText"
        :placeholder="computedPlaceholder"
        :disabled="disabled"
        class="selector-input"
        @focus="handleInputFocus"
        @blur="handleInputBlur"
        @input="handleSearchInput"
      />
    </div>
    
    <transition name="dropdown">
      <div v-if="showDropdown && options.length > 0" class="value-help-dropdown">
        <div class="dropdown-search">
          <input
            v-model="dropdownSearch"
            placeholder="搜索..."
            class="dropdown-search-input"
            @mousedown.stop
          />
        </div>
        <div class="dropdown-list">
          <div
            v-for="opt in filteredOptions"
            :key="opt.id"
            class="dropdown-item"
            :class="{ selected: isOptionSelected(opt) }"
            @mousedown.prevent="handleSelectOption(opt)"
          >
            <span class="item-checkbox">
              <AppIcon :name="isOptionSelected(opt) ? 'check-square' : 'square'" :size="12" />
            </span>
            <span class="item-name">{{ opt.display_name }}</span>
            <span v-if="opt.path" class="item-path">{{ opt.path }}</span>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import AppIcon from '../AppIcon/AppIcon.vue'

const props = defineProps({
  modelValue: {
    type: [String, Number, Array],
    default: ''
  },
  displayValue: {
    type: String,
    default: ''
  },
  options: {
    type: Array,
    default: () => []
  },
  multiple: {
    type: Boolean,
    default: false
  },
  disabled: {
    type: Boolean,
    default: false
  },
  placeholder: {
    type: String,
    default: ''
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'update:displayValue', 'search', 'focus', 'blur', 'change'])

const inputRef = ref(null)
const searchText = ref('')
const dropdownSearch = ref('')
const showDropdown = ref(false)
const selectedValues = ref([])
let searchTimeout = null

const computedPlaceholder = computed(() => {
  if (props.disabled) return ''
  if (props.multiple && selectedValues.value.length > 0) return ''
  if (!props.multiple && props.displayValue) return ''
  return props.placeholder || '请选择...'
})

const filteredOptions = computed(() => {
  if (!dropdownSearch.value) return props.options
  const query = dropdownSearch.value.toLowerCase()
  return props.options.filter(opt => 
    opt.display_name?.toLowerCase().includes(query) ||
    opt.path?.toLowerCase().includes(query)
  )
})

function isOptionSelected(opt) {
  if (props.multiple) {
    return selectedValues.value.some(v => String(v.id) === String(opt.id))
  }
  return String(props.modelValue) === String(opt.id)
}

function handleFocus() {
  if (props.disabled) return
  inputRef.value?.focus()
}

function handleInputFocus() {
  if (props.disabled) return
  showDropdown.value = true
  emit('focus')
}

function handleInputBlur() {
  setTimeout(() => {
    showDropdown.value = false
    emit('blur')
  }, 200)
}

function handleSearchInput() {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    emit('search', searchText.value)
  }, 300)
}

function handleSelectOption(opt) {
  if (props.multiple) {
    const idx = selectedValues.value.findIndex(v => String(v.id) === String(opt.id))
    if (idx >= 0) {
      selectedValues.value.splice(idx, 1)
    } else {
      selectedValues.value.push({ id: opt.id, display_name: opt.display_name })
    }
    emit('update:modelValue', selectedValues.value.map(v => v.id))
    emit('change', selectedValues.value)
  } else {
    emit('update:modelValue', opt.id)
    emit('update:displayValue', opt.display_name)
    emit('change', { id: opt.id, display_name: opt.display_name })
    showDropdown.value = false
  }
}

function removeTag(tag) {
  const idx = selectedValues.value.findIndex(v => String(v.id) === String(tag.id))
  if (idx >= 0) {
    selectedValues.value.splice(idx, 1)
    emit('update:modelValue', selectedValues.value.map(v => v.id))
    emit('change', selectedValues.value)
  }
}

function clearValue() {
  emit('update:modelValue', '')
  emit('update:displayValue', '')
  emit('change', null)
}

watch(() => props.modelValue, (newVal) => {
  if (props.multiple && Array.isArray(newVal)) {
    const existingIds = selectedValues.value.map(v => String(v.id))
    const newIds = newVal.map(v => String(v))
    
    if (JSON.stringify(existingIds) !== JSON.stringify(newIds)) {
      selectedValues.value = newVal.map(id => {
        const opt = props.options.find(o => String(o.id) === String(id))
        return { id, display_name: opt?.display_name || id }
      })
    }
  }
}, { immediate: true, deep: true })

onUnmounted(() => {
  if (searchTimeout) clearTimeout(searchTimeout)
})
</script>

<style scoped>
.value-help-selector {
  position: relative;
  width: 100%;
}

.value-help-selector--disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.selected-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-container);
  min-height: 36px;
  cursor: pointer;
  transition: border-color var(--transition-fast);
}

.selected-tags:hover {
  border-color: var(--color-primary);
}

.value-help-selector--disabled .selected-tags {
  cursor: not-allowed;
  background: var(--color-bg-disabled);
}

.value-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: var(--color-primary-bg);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  color: var(--color-primary);
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.single-tag {
  cursor: default;
  max-width: 200px;
}

.tag-remove {
  border: none;
  background: transparent;
  color: var(--color-primary);
  cursor: pointer;
  font-size: 14px;
  padding: 0;
  line-height: 1;
  flex-shrink: 0;
}

.tag-remove:hover {
  color: var(--color-error);
}

.selector-input {
  border: none;
  background: transparent;
  outline: none;
  flex: 1;
  min-width: 60px;
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
}

.selector-input::placeholder {
  color: var(--color-text-placeholder);
}

.value-help-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: var(--color-bg-container);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  z-index: 100;
  max-height: 280px;
  overflow-y: auto;
  margin-top: 2px;
}

.dropdown-search {
  padding: var(--spacing-xs) var(--spacing-sm);
  border-bottom: 1px solid var(--color-border);
  position: sticky;
  top: 0;
  background: var(--color-bg-container);
}

.dropdown-search-input {
  width: 100%;
  padding: var(--spacing-xs) var(--spacing-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  background: var(--color-bg-base);
  color: var(--color-text-primary);
}

.dropdown-search-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.dropdown-list {
  padding: var(--spacing-xs) 0;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-xs) var(--spacing-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
  transition: background var(--transition-fast);
}

.dropdown-item:hover {
  background: var(--color-primary-bg);
}

.dropdown-item.selected {
  background: var(--color-primary-bg-subtle);
}

.item-checkbox {
  font-size: var(--font-size-sm);
  color: var(--color-primary);
  width: 20px;
  flex-shrink: 0;
}

.item-name {
  color: var(--color-text-primary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-path {
  color: var(--color-text-quaternary);
  font-size: var(--font-size-xs);
  margin-left: auto;
  flex-shrink: 0;
}

.dropdown-enter-active,
.dropdown-leave-active {
  transition: opacity var(--transition-fast), transform var(--transition-fast);
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
