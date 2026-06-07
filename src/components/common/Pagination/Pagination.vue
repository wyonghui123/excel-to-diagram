<template>
  <div class="pagination">
    <div v-if="showTotal" class="pagination__total">
      共 {{ total }} 条
    </div>

    <div class="pagination__pager">
      <button
        class="pagination__btn pagination__btn--nav"
        :disabled="current === 1"
        @click="goToPage(1)"
        title="首页"
      >
        <svg viewBox="0 0 24 24" width="14" height="14">
          <path fill="currentColor" d="M18.41 16.59L13.82 12l4.59-4.59L17 6l-6 6 6 6zM6 6h2v12H6z"/>
        </svg>
      </button>

      <button
        class="pagination__btn pagination__btn--nav"
        :disabled="current === 1"
        @click="goToPage(current - 1)"
        title="上一页"
      >
        <svg viewBox="0 0 24 24" width="14" height="14">
          <path fill="currentColor" d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z"/>
        </svg>
      </button>

      <template v-for="page in displayedPages" :key="page">
        <button
          v-if="page === 'prev-ellipsis' || page === 'next-ellipsis'"
          class="pagination__btn pagination__btn--ellipsis"
          disabled
        >
          ...
        </button>
        <button
          v-else
          class="pagination__btn"
          :class="{ 'pagination__btn--active': page === current }"
          @click="goToPage(page)"
        >
          {{ page }}
        </button>
      </template>

      <button
        class="pagination__btn pagination__btn--nav"
        :disabled="current === pageCount"
        @click="goToPage(current + 1)"
        title="下一页"
      >
        <svg viewBox="0 0 24 24" width="14" height="14">
          <path fill="currentColor" d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/>
        </svg>
      </button>

      <button
        class="pagination__btn pagination__btn--nav"
        :disabled="current === pageCount"
        @click="goToPage(pageCount)"
        title="末页"
      >
        <svg viewBox="0 0 24 24" width="14" height="14">
          <path fill="currentColor" d="M5.59 7.41L10.18 12l-4.59 4.59L7 18l6-6-6-6zM16 6h2v12h-2z"/>
        </svg>
      </button>
    </div>

    <div v-if="showSizeChanger" class="pagination__size-changer">
      <select
        :value="pageSize"
        class="pagination__select"
        @change="handlePageSizeChange"
      >
        <option
          v-for="size in pageSizeOptions"
          :key="size"
          :value="size"
        >
          {{ size }} 条/页
        </option>
      </select>
    </div>

    <div v-if="showQuickJumper" class="pagination__jumper">
      <span>跳至</span>
      <input
        type="number"
        class="pagination__jumper-input"
        :min="1"
        :max="pageCount"
        :value="jumperValue"
        @input="handleJumperInput"
        @keyup.enter="handleJumperJump"
      />
      <span>页</span>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  current: {
    type: Number,
    default: 1,
    validator: (value) => value >= 1
  },
  total: {
    type: Number,
    default: 0,
    validator: (value) => value >= 0
  },
  pageSize: {
    type: Number,
    default: 10,
    validator: (value) => value > 0
  },
  showSizeChanger: {
    type: Boolean,
    default: true
  },
  showQuickJumper: {
    type: Boolean,
    default: false
  },
  pageSizeOptions: {
    type: Array,
    default: () => [10, 20, 50, 100]
  },
  showTotal: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits([
  'update:current',
  'update:pageSize',
  'change',
  'pageSizeChange'
])

const jumperValue = ref(props.current)

const pageCount = computed(() => {
  return Math.max(1, Math.ceil(props.total / props.pageSize))
})

const displayedPages = computed(() => {
  const pages = []
  const total = pageCount.value
  const current = props.current

  if (total <= 7) {
    for (let i = 1; i <= total; i++) {
      pages.push(i)
    }
  } else {
    if (current <= 4) {
      for (let i = 1; i <= 5; i++) {
        pages.push(i)
      }
      pages.push('next-ellipsis')
      pages.push(total)
    } else if (current >= total - 3) {
      pages.push(1)
      pages.push('prev-ellipsis')
      for (let i = total - 4; i <= total; i++) {
        pages.push(i)
      }
    } else {
      pages.push(1)
      pages.push('prev-ellipsis')
      for (let i = current - 1; i <= current + 1; i++) {
        pages.push(i)
      }
      pages.push('next-ellipsis')
      pages.push(total)
    }
  }

  return pages
})

watch(() => props.current, (newVal) => {
  jumperValue.value = newVal
})

const goToPage = (page) => {
  const validPage = Math.max(1, Math.min(page, pageCount.value))
  if (validPage !== props.current) {
    emit('update:current', validPage)
    emit('change', validPage)
  }
}

const handlePageSizeChange = (event) => {
  const newSize = parseInt(event.target.value, 10)
  emit('update:pageSize', newSize)
  emit('pageSizeChange', newSize)

  const newPageCount = Math.ceil(props.total / newSize)
  if (props.current > newPageCount) {
    const newPage = Math.max(1, newPageCount)
    emit('update:current', newPage)
    emit('change', newPage)
  }
}

const handleJumperInput = (event) => {
  jumperValue.value = event.target.value
}

const handleJumperJump = () => {
  const page = parseInt(jumperValue.value, 10)
  if (!isNaN(page) && page >= 1 && page <= pageCount.value) {
    goToPage(page)
  } else {
    jumperValue.value = props.current
  }
}
</script>

<style scoped>
.pagination {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  font-family: var(--font-family);
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
}

.pagination__total {
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.pagination__pager {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.pagination__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 32px;
  height: 32px;
  padding: 0 var(--spacing-xs);
  font-family: var(--font-family);
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  background: var(--color-bg-base);
  border: var(--border-width-thin) solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition-fast);
  user-select: none;
}

.pagination__btn:hover:not(:disabled):not(.pagination__btn--ellipsis) {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.pagination__btn:focus-visible {
  outline: none;
  box-shadow: var(--shadow-focus);
}

.pagination__btn--active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--color-text-inverse);
}

.pagination__btn--active:hover {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
  color: var(--color-text-inverse);
}

.pagination__btn--nav {
  padding: 0;
}

.pagination__btn--ellipsis {
  border: none;
  background: transparent;
  cursor: default;
  min-width: 32px;
}

.pagination__btn:disabled:not(.pagination__btn--ellipsis) {
  color: var(--color-text-disabled);
  background: var(--color-bg-disabled);
  border-color: var(--color-border-secondary);
  cursor: not-allowed;
}

.pagination__size-changer {
  display: flex;
  align-items: center;
}

.pagination__select {
  height: 32px;
  padding: 0 var(--spacing-lg) 0 var(--spacing-sm);
  font-family: var(--font-family);
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  background: var(--color-bg-base);
  border: var(--border-width-thin) solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  outline: none;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' width='16' height='16'%3E%3Cpath fill='%23666' d='M7 10l5 5 5-5z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 4px center;
}

.pagination__select:hover {
  border-color: var(--color-primary);
}

.pagination__select:focus {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.pagination__jumper {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.pagination__jumper-input {
  width: 50px;
  height: 32px;
  padding: 0 var(--spacing-sm);
  font-family: var(--font-family);
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  text-align: center;
  background: var(--color-bg-base);
  border: var(--border-width-thin) solid var(--color-border);
  border-radius: var(--radius-sm);
  outline: none;
  appearance: textfield;
}

.pagination__jumper-input::-webkit-outer-spin-button,
.pagination__jumper-input::-webkit-inner-spin-button {
  appearance: none;
  margin: 0;
}

.pagination__jumper-input:hover {
  border-color: var(--color-primary);
}

.pagination__jumper-input:focus {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}
</style>
