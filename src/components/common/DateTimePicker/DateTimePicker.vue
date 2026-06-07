<template>
  <div :class="wrapperClasses">
    <label v-if="label" class="datetime-picker__label">
      {{ label }}
      <span v-if="required" class="datetime-picker__required">*</span>
    </label>
    <div class="datetime-picker__wrapper">
      <div class="datetime-picker__input-wrapper" @click="openPicker">
        <span class="datetime-picker__prefix">
          <svg viewBox="0 0 24 24" width="16" height="16">
            <path fill="currentColor" d="M19 3h-1V1h-2v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM9 10H7v2h2v-2zm4 0h-2v2h2v-2zm4 0h-2v2h2v-2zm-8 4H7v2h2v-2zm4 0h-2v2h2v-2zm4 0h-2v2h2v-2z"/>
          </svg>
        </span>
        <input
          ref="inputRef"
          :class="inputClasses"
          :value="displayValue"
          :placeholder="placeholder"
          :disabled="disabled"
          :readonly="true"
          @focus="handleFocus"
          @blur="handleBlur"
        />
        <span v-if="clearable && modelValue" class="datetime-picker__suffix">
          <button
            type="button"
            class="datetime-picker__clear"
            @click.stop="handleClear"
          >
            <svg viewBox="0 0 24 24" width="14" height="14">
              <path fill="currentColor" d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
            </svg>
          </button>
        </span>
        <span v-else class="datetime-picker__suffix">
          <svg viewBox="0 0 24 24" width="16" height="16">
            <path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
          </svg>
        </span>
      </div>

      <!-- 日期时间选择面板 -->
      <transition name="datetime-picker-dropdown">
        <div v-if="isOpen" class="datetime-picker__dropdown" @click.stop>
          <!-- 日期选择区域 -->
          <div class="datetime-picker__date-section">
            <div class="datetime-picker__header">
              <button type="button" class="datetime-picker__nav-btn" @click="prevMonth">
                <svg viewBox="0 0 24 24" width="16" height="16">
                  <path fill="currentColor" d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z"/>
                </svg>
              </button>
              <div class="datetime-picker__selectors">
                <select v-model.number="currentYear" class="datetime-picker__year-select" @change="onYearChange">
                  <option v-for="year in yearOptions" :key="year" :value="year">{{ year }}年</option>
                </select>
                <select v-model.number="currentMonth" class="datetime-picker__month-select" @change="onMonthChange">
                  <option v-for="month in 12" :key="month" :value="month - 1">{{ month }}月</option>
                </select>
              </div>
              <button type="button" class="datetime-picker__nav-btn" @click="nextMonth">
                <svg viewBox="0 0 24 24" width="16" height="16">
                  <path fill="currentColor" d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/>
                </svg>
              </button>
            </div>
            <div class="datetime-picker__weekdays">
              <span v-for="day in weekdays" :key="day" class="datetime-picker__weekday">{{ day }}</span>
            </div>
            <div class="datetime-picker__days">
              <button
                v-for="date in calendarDays"
                :key="date.date"
                type="button"
                :class="dayClasses(date)"
                @click="selectDate(date)"
              >
                {{ date.day }}
              </button>
            </div>
          </div>

          <!-- 时间选择区域 -->
          <div v-if="showTime" class="datetime-picker__time-section">
            <div class="datetime-picker__time-title">时间</div>
            <div class="datetime-picker__time-inputs">
              <div class="datetime-picker__time-field">
                <input
                  v-model.number="selectedHour"
                  type="number"
                  min="0"
                  max="23"
                  class="datetime-picker__time-input"
                  @input="handleTimeInput('hour', $event)"
                />
                <span class="datetime-picker__time-separator">:</span>
                <input
                  v-model.number="selectedMinute"
                  type="number"
                  min="0"
                  max="59"
                  class="datetime-picker__time-input"
                  @input="handleTimeInput('minute', $event)"
                />
                <span v-if="showSeconds" class="datetime-picker__time-separator">:</span>
                <input
                  v-if="showSeconds"
                  v-model.number="selectedSecond"
                  type="number"
                  min="0"
                  max="59"
                  class="datetime-picker__time-input"
                  @input="handleTimeInput('second', $event)"
                />
              </div>
            </div>
          </div>

          <!-- 底部按钮 -->
          <div class="datetime-picker__footer">
            <button type="button" class="datetime-picker__btn datetime-picker__btn--now" @click="selectNow">
              此刻
            </button>
            <div class="datetime-picker__footer-actions">
              <button type="button" class="datetime-picker__btn datetime-picker__btn--cancel" @click="closePicker">
                取消
              </button>
              <button type="button" class="datetime-picker__btn datetime-picker__btn--confirm" @click="confirmSelection">
                确定
              </button>
            </div>
          </div>
        </div>
      </transition>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'

const props = defineProps({
  /**
   * 选中值（v-model）- ISO 格式字符串或 Date 对象
   */
  modelValue: {
    type: [String, Date, Number],
    default: null
  },
  /**
   * 占位符文本
   */
  placeholder: {
    type: String,
    default: '请选择日期时间'
  },
  /**
   * 标签文本
   */
  label: {
    type: String,
    default: ''
  },
  /**
   * 尺寸
   * @values 'sm' | 'md' | 'lg'
   */
  size: {
    type: String,
    default: 'md',
    validator: (value) => ['sm', 'md', 'lg'].includes(value)
  },
  /**
   * 是否禁用
   */
  disabled: {
    type: Boolean,
    default: false
  },
  /**
   * 是否可清空
   */
  clearable: {
    type: Boolean,
    default: true
  },
  /**
   * 是否显示时间选择
   */
  showTime: {
    type: Boolean,
    default: true
  },
  /**
   * 是否显示秒
   */
  showSeconds: {
    type: Boolean,
    default: false
  },
  /**
   * 是否必填
   */
  required: {
    type: Boolean,
    default: false
  },
  /**
   * 日期时间格式
   */
  format: {
    type: String,
    default: 'yyyy-MM-dd HH:mm'
  }
})

const emit = defineEmits(['update:modelValue', 'change', 'focus', 'blur', 'clear'])

const inputRef = ref(null)
const isOpen = ref(false)
const isFocused = ref(false)
const currentYear = ref(new Date().getFullYear())
const currentMonth = ref(new Date().getMonth())
const selectedDate = ref(null)
const selectedHour = ref(0)
const selectedMinute = ref(0)
const selectedSecond = ref(0)

const weekdays = ['日', '一', '二', '三', '四', '五', '六']

const wrapperClasses = computed(() => [
  'datetime-picker',
  `datetime-picker--${props.size}`,
  {
    'datetime-picker--disabled': props.disabled,
    'datetime-picker--focused': isFocused.value,
    'datetime-picker--open': isOpen.value
  }
])

const inputClasses = computed(() => [
  'datetime-picker__input',
  `datetime-picker__input--${props.size}`
])

const displayValue = computed(() => {
  if (!props.modelValue) return ''
  const date = new Date(props.modelValue)
  if (isNaN(date.getTime())) return ''
  
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hour = String(date.getHours()).padStart(2, '0')
  const minute = String(date.getMinutes()).padStart(2, '0')
  const second = String(date.getSeconds()).padStart(2, '0')
  
  if (props.showTime) {
    if (props.showSeconds) {
      return `${year}-${month}-${day} ${hour}:${minute}:${second}`
    }
    return `${year}-${month}-${day} ${hour}:${minute}`
  }
  return `${year}-${month}-${day}`
})

const yearOptions = computed(() => {
  const currentYearNow = new Date().getFullYear()
  const years = []
  for (let year = currentYearNow - 10; year <= currentYearNow + 10; year++) {
    years.push(year)
  }
  return years
})

const calendarDays = computed(() => {
  const days = []
  const firstDayOfMonth = new Date(currentYear.value, currentMonth.value, 1)
  const lastDayOfMonth = new Date(currentYear.value, currentMonth.value + 1, 0)
  const startDayOfWeek = firstDayOfMonth.getDay()
  const daysInMonth = lastDayOfMonth.getDate()
  
  // 上个月的日期
  const prevMonthLastDay = new Date(currentYear.value, currentMonth.value, 0).getDate()
  for (let i = startDayOfWeek - 1; i >= 0; i--) {
    const day = prevMonthLastDay - i
    const date = new Date(currentYear.value, currentMonth.value - 1, day)
    days.push({
      date: date.toISOString(),
      day,
      isCurrentMonth: false,
      isToday: isSameDay(date, new Date()),
      isSelected: selectedDate.value && isSameDay(date, selectedDate.value)
    })
  }
  
  // 当前月的日期
  for (let day = 1; day <= daysInMonth; day++) {
    const date = new Date(currentYear.value, currentMonth.value, day)
    days.push({
      date: date.toISOString(),
      day,
      isCurrentMonth: true,
      isToday: isSameDay(date, new Date()),
      isSelected: selectedDate.value && isSameDay(date, selectedDate.value)
    })
  }
  
  // 下个月的日期
  const remainingDays = 42 - days.length
  for (let day = 1; day <= remainingDays; day++) {
    const date = new Date(currentYear.value, currentMonth.value + 1, day)
    days.push({
      date: date.toISOString(),
      day,
      isCurrentMonth: false,
      isToday: isSameDay(date, new Date()),
      isSelected: selectedDate.value && isSameDay(date, selectedDate.value)
    })
  }
  
  return days
})

const isSameDay = (date1, date2) => {
  return date1.getFullYear() === date2.getFullYear() &&
         date1.getMonth() === date2.getMonth() &&
         date1.getDate() === date2.getDate()
}

const dayClasses = (date) => [
  'datetime-picker__day',
  {
    'datetime-picker__day--other-month': !date.isCurrentMonth,
    'datetime-picker__day--today': date.isToday,
    'datetime-picker__day--selected': date.isSelected
  }
]

const openPicker = () => {
  if (props.disabled) return
  isOpen.value = true
  isFocused.value = true
  emit('focus')
  
  // 初始化选中值
  if (props.modelValue) {
    const date = new Date(props.modelValue)
    if (!isNaN(date.getTime())) {
      selectedDate.value = date
      currentYear.value = date.getFullYear()
      currentMonth.value = date.getMonth()
      selectedHour.value = date.getHours()
      selectedMinute.value = date.getMinutes()
      selectedSecond.value = date.getSeconds()
    }
  }
}

const closePicker = () => {
  isOpen.value = false
  isFocused.value = false
  emit('blur')
}

const handleFocus = () => {
  if (!props.disabled) {
    isFocused.value = true
  }
}

const handleBlur = () => {
  // 延迟关闭，以便点击下拉面板
  setTimeout(() => {
    if (!isOpen.value) {
      isFocused.value = false
      emit('blur')
    }
  }, 200)
}

const handleClear = () => {
  emit('update:modelValue', null)
  emit('change', null)
  emit('clear')
  selectedDate.value = null
}

const prevMonth = () => {
  if (currentMonth.value === 0) {
    currentMonth.value = 11
    currentYear.value--
  } else {
    currentMonth.value--
  }
}

const nextMonth = () => {
  if (currentMonth.value === 11) {
    currentMonth.value = 0
    currentYear.value++
  } else {
    currentMonth.value++
  }
}

const onYearChange = () => {
}

const onMonthChange = () => {
}

const selectDate = (date) => {
  const newDate = new Date(date.date)
  if (selectedDate.value) {
    newDate.setHours(selectedHour.value)
    newDate.setMinutes(selectedMinute.value)
    newDate.setSeconds(selectedSecond.value)
  }
  selectedDate.value = newDate
  currentYear.value = newDate.getFullYear()
  currentMonth.value = newDate.getMonth()
}

const handleTimeInput = (type, event) => {
  let value = parseInt(event.target.value) || 0
  
  if (type === 'hour') {
    value = Math.max(0, Math.min(23, value))
    selectedHour.value = value
  } else if (type === 'minute') {
    value = Math.max(0, Math.min(59, value))
    selectedMinute.value = value
  } else if (type === 'second') {
    value = Math.max(0, Math.min(59, value))
    selectedSecond.value = value
  }
  
  event.target.value = String(value).padStart(2, '0')
}

const selectNow = () => {
  const now = new Date()
  selectedDate.value = now
  currentYear.value = now.getFullYear()
  currentMonth.value = now.getMonth()
  selectedHour.value = now.getHours()
  selectedMinute.value = now.getMinutes()
  selectedSecond.value = now.getSeconds()
  
  const result = props.showTime ? now : new Date(now.getFullYear(), now.getMonth(), now.getDate())
  emit('update:modelValue', result.toISOString())
  emit('change', result.toISOString())
  closePicker()
}

const confirmSelection = () => {
  // 如果没有选择日期，使用当前日期
  let result
  if (selectedDate.value) {
    result = new Date(selectedDate.value)
  } else {
    result = new Date()
    result.setFullYear(currentYear.value)
    result.setMonth(currentMonth.value)
    result.setDate(1)
  }
  
  if (props.showTime) {
    result.setHours(selectedHour.value)
    result.setMinutes(selectedMinute.value)
    result.setSeconds(selectedSecond.value)
  } else {
    result.setHours(0, 0, 0, 0)
  }
  
  const isoString = result.toISOString()
  emit('update:modelValue', isoString)
  emit('change', isoString)
  closePicker()
}

const handleClickOutside = (event) => {
  const wrapper = inputRef.value?.closest('.datetime-picker')
  if (wrapper && !wrapper.contains(event.target)) {
    closePicker()
  }
}

// 使用 mousedown 事件，避免与 click 事件冲突
onMounted(() => {
  document.addEventListener('mousedown', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', handleClickOutside)
})

watch(() => props.modelValue, (newVal) => {
  if (newVal) {
    const date = new Date(newVal)
    if (!isNaN(date.getTime())) {
      selectedDate.value = date
      selectedHour.value = date.getHours()
      selectedMinute.value = date.getMinutes()
      selectedSecond.value = date.getSeconds()
    }
  } else {
    selectedDate.value = null
  }
}, { immediate: true })
</script>

<style scoped>
.datetime-picker {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  width: 100%;
  position: relative;
}

.datetime-picker__label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  line-height: var(--line-height-normal);
}

.datetime-picker__required {
  color: var(--color-error);
  margin-left: var(--spacing-xxs);
}

.datetime-picker__wrapper {
  position: relative;
}

.datetime-picker__input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  cursor: pointer;
}

.datetime-picker__prefix {
  position: absolute;
  left: var(--spacing-sm);
  display: flex;
  align-items: center;
  color: var(--color-text-tertiary);
  z-index: 1;
}

.datetime-picker__suffix {
  position: absolute;
  right: var(--spacing-sm);
  display: flex;
  align-items: center;
  color: var(--color-text-tertiary);
  z-index: 1;
}

.datetime-picker__input {
  width: 100%;
  font-family: var(--font-family);
  color: var(--color-text-primary);
  background: var(--color-bg-base);
  border: var(--border-width-thin) solid var(--color-border);
  border-radius: var(--radius-input);
  transition: var(--transition-normal);
  outline: none;
  cursor: pointer;
}

.datetime-picker__input::placeholder {
  color: var(--color-text-placeholder);
}

.datetime-picker__input:hover:not(:disabled) {
  border-color: var(--color-primary);
}

.datetime-picker--focused .datetime-picker__input,
.datetime-picker--open .datetime-picker__input {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.datetime-picker--disabled .datetime-picker__input {
  background: var(--color-bg-disabled);
  color: var(--color-text-disabled);
  cursor: not-allowed;
}

/* 尺寸变体 */
.datetime-picker__input--sm {
  height: var(--input-height-sm);
  padding: 0 var(--spacing-sm);
  padding-left: calc(var(--spacing-sm) + 24px);
  padding-right: calc(var(--spacing-sm) + 24px);
  font-size: var(--font-size-sm);
}

.datetime-picker__input--md {
  height: var(--input-height-md);
  padding: 0 var(--spacing-md);
  padding-left: calc(var(--spacing-md) + 24px);
  padding-right: calc(var(--spacing-md) + 24px);
  font-size: var(--font-size-md);
}

.datetime-picker__input--lg {
  height: var(--input-height-lg);
  padding: 0 var(--spacing-lg);
  padding-left: calc(var(--spacing-lg) + 24px);
  padding-right: calc(var(--spacing-lg) + 24px);
  font-size: var(--font-size-lg);
}

/* 清空按钮 */
.datetime-picker__clear {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  cursor: pointer;
  transition: var(--transition-fast);
}

.datetime-picker__clear:hover {
  color: var(--color-text-secondary);
}

/* 下拉面板 */
.datetime-picker__dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: var(--spacing-xs);
  background: var(--color-bg-container);
  border: var(--border-width-thin) solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  z-index: var(--z-index-dropdown, 1000);
  min-width: 280px;
  padding: var(--spacing-md);
}

/* 日期选择区域 */
.datetime-picker__date-section {
  margin-bottom: var(--spacing-md);
}

.datetime-picker__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-sm);
}

.datetime-picker__selectors {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.datetime-picker__year-select,
.datetime-picker__month-select {
  padding: 4px 8px;
  font-size: var(--font-size-sm);
  font-family: var(--font-family);
  color: var(--color-text-primary);
  background: var(--color-bg-base);
  border: var(--border-width-thin) solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  outline: none;
  transition: var(--transition-fast);
}

.datetime-picker__year-select:hover,
.datetime-picker__month-select:hover {
  border-color: var(--color-primary);
}

.datetime-picker__year-select:focus,
.datetime-picker__month-select:focus {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.datetime-picker__nav-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  background: none;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: var(--transition-fast);
}

.datetime-picker__nav-btn:hover {
  background: var(--color-bg-secondary);
  color: var(--color-primary);
}

.datetime-picker__current-month {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.datetime-picker__weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: var(--spacing-xs);
  margin-bottom: var(--spacing-xs);
}

.datetime-picker__weekday {
  text-align: center;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  padding: var(--spacing-xs);
}

.datetime-picker__days {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: var(--spacing-xs);
}

.datetime-picker__day {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 32px;
  padding: 0;
  background: none;
  border: none;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  cursor: pointer;
  transition: var(--transition-fast);
}

.datetime-picker__day:hover:not(.datetime-picker__day--selected) {
  background: var(--color-bg-secondary);
}

.datetime-picker__day--other-month {
  color: var(--color-text-quaternary);
}

.datetime-picker__day--today {
  color: var(--color-primary);
  font-weight: var(--font-weight-medium);
}

.datetime-picker__day--selected {
  background: var(--color-primary);
  color: white;
}

/* 时间选择区域 */
.datetime-picker__time-section {
  border-top: var(--border-width-thin) solid var(--color-border-light);
  padding-top: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.datetime-picker__time-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-sm);
}

.datetime-picker__time-inputs {
  display: flex;
  align-items: center;
  justify-content: center;
}

.datetime-picker__time-field {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.datetime-picker__time-input {
  width: 48px;
  height: 32px;
  padding: 0 var(--spacing-xs);
  text-align: center;
  font-family: var(--font-family);
  font-size: var(--font-size-md);
  color: var(--color-text-primary);
  background: var(--color-bg-base);
  border: var(--border-width-thin) solid var(--color-border);
  border-radius: var(--radius-sm);
  outline: none;
}

.datetime-picker__time-input:focus {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.datetime-picker__time-separator {
  font-size: var(--font-size-md);
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
}

/* 底部按钮 */
.datetime-picker__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: var(--border-width-thin) solid var(--color-border-light);
  padding-top: var(--spacing-md);
}

.datetime-picker__footer-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.datetime-picker__btn {
  padding: var(--spacing-xs) var(--spacing-md);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition-fast);
  border: var(--border-width-thin) solid transparent;
}

.datetime-picker__btn--now {
  background: transparent;
  color: var(--color-primary);
  border-color: var(--color-primary);
}

.datetime-picker__btn--now:hover {
  background: var(--color-primary-bg);
}

.datetime-picker__btn--cancel {
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  border-color: var(--color-border);
}

.datetime-picker__btn--cancel:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.datetime-picker__btn--confirm {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}

.datetime-picker__btn--confirm:hover {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
}

/* 动画 */
.datetime-picker-dropdown-enter-active,
.datetime-picker-dropdown-leave-active {
  transition: opacity var(--transition-fast), transform var(--transition-fast);
}

.datetime-picker-dropdown-enter-from,
.datetime-picker-dropdown-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
