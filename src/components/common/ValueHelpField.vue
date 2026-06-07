<template>
  <div class="value-help-field">
    <template v-if="resultType === 'dropdown'">
      <!-- 单选：不用 filterable，el-select 会自动根据 v-model 匹配 option 显示 label -->
      <el-select
        v-if="!isMultiple"
        v-model="internalValue"
        :loading="loading"
        :disabled="disabled || !bindingSatisfied"
        :placeholder="placeholder"
        :clearable="true"
        style="width: 100%"
        @update:model-value="handleSelectChange"
        @visible-change="handleDropdownVisible"
      >
        <el-option
          v-for="opt in optionsList"
          :key="opt.value"
          :label="opt.display"
          :value="opt.value"
        />
      </el-select>
      <!-- 多选 -->
      <el-select
        v-else
        v-model="internalValue"
        multiple
        filterable
        remote
        :remote-method="handleRemoteSearch"
        :loading="loading"
        :disabled="disabled || !bindingSatisfied"
        :placeholder="placeholder"
        :clearable="true"
        :collapse-tags="true"
        :collapse-tags-tooltip="true"
        style="width: 100%"
        @update:model-value="handleSelectChange"
        @visible-change="handleDropdownVisible"
      >
        <el-option
          v-for="opt in optionsList"
          :key="opt.value"
          :label="opt.display"
          :value="opt.value"
        />
      </el-select>
    </template>

    <template v-else-if="resultType === 'dialog'">
      <el-input
        :model-value="displayValue"
        :disabled="disabled"
        :placeholder="placeholder"
        readonly
        @click="handleDialogOpen"
        style="width: 100%"
      >
        <template #suffix>
          <el-icon class="vh-search-icon" @click="handleDialogOpen">
            <Search />
          </el-icon>
        </template>
      </el-input>
      <SearchHelpDialog
        v-model:visible="dialogVisible"
        :value-help-config="valueHelpConfig"
        :multiple="isMultiple"
        :selected-value="modelValue"
        @confirm="handleDialogConfirm"
      />
    </template>

    <template v-else-if="resultType === 'inline'">
      <el-autocomplete
        :model-value="displayValue"
        :fetch-suggestions="handleAutocomplete"
        :disabled="disabled || !bindingSatisfied"
        :placeholder="placeholder"
        :trigger-on-focus="minSearchLength === 0"
        @select="handleAutocompleteSelect"
        @input="handleAutocompleteInput"
        style="width: 100%"
        popper-class="vh-autocomplete-popper"
      />
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick, getCurrentInstance } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { useValueHelp } from '@/composables/useValueHelp'
import SearchHelpDialog from './SearchHelpDialog.vue'

const props = defineProps({
  modelValue: { type: [String, Number, Array], default: '' },
  valueHelpConfig: { type: Object, required: true },
  disabled: { type: Boolean, default: false },
  placeholder: { type: String, default: '请选择' },
  formValues: { type: Object, default: () => ({}) },
  fieldKey: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'update:displayValue', 'change', 'out-mapping'])

const instance = getCurrentInstance()

const dialogVisible = ref(false)

const {
  optionsList,
  loading,
  displayValue,
  loadOptions,
  loadOptionsDebounced,
  resolveDisplay,
  validateInput,
  getFilterParams,
  isBindingSatisfied,
  outMappings,
  applyOutMappings,
  saveRecentItem,
} = useValueHelp(props.valueHelpConfig)

const resultType = computed(() => {
  return props.valueHelpConfig?.presentation?.result_type || 'dropdown'
})

const isMultiple = computed(() => {
  return props.valueHelpConfig?.behavior?.multiple === true
})

const minSearchLength = computed(() => {
  return props.valueHelpConfig?.behavior?.min_search_length || 0
})

const bindingSatisfied = computed(() => {
  return isBindingSatisfied(props.formValues)
})

// 关键：先设 null，等 onMounted 后 el-option 渲染完成再设真实值
// 这样 el-select 才能找到匹配的 option 并显示 label
const internalValue = ref(null)

onMounted(() => {
  nextTick(() => {
    if (props.modelValue != null && props.modelValue !== '' &&
        !(Array.isArray(props.modelValue) && props.modelValue.length === 0)) {
      internalValue.value = props.modelValue
    }
  })
  // 预加载 options，让 filterable 本地搜索能工作
  // handleDropdownVisible 只在用户点击 el-select 时触发，但 el-select 不会在 mount 时触发
  // 注意：optionsList 可能有 initial_options（详情页编辑态），仍要预加载全部选项，否则下拉只显示当前值
  if (bindingSatisfied.value) {
    const filters = getFilterParams(props.formValues)
    loadOptions('', { filters, pageSize: 200 })
  }
})

watch(() => props.modelValue, (val) => {
  internalValue.value = val
})

// optionsList 异步更新后，重新触发 el-select 匹配
watch(optionsList, async () => {
  if (internalValue.value != null && internalValue.value !== '') {
    const val = internalValue.value
    internalValue.value = null
    await nextTick()
    internalValue.value = val
  }
}, { deep: true })

watch(() => props.modelValue, (val) => {
  const isEmpty = val === null || val === undefined || val === '' ||
                  (Array.isArray(val) && val.length === 0)
  if (!isEmpty) {
    resolveDisplay(val)
  } else {
    displayValue.value = ''
  }
})

watch(() => {
  const bindings = props.valueHelpConfig?.behavior?.parameter_bindings || []
  return bindings
    .filter(b => b.local_field)
    .map(b => `${b.local_field}=${props.formValues[b.local_field]}`)
    .join('|')
}, (newKey, oldKey) => {
  if (newKey !== oldKey) {
    optionsList.value = []
    if (bindingSatisfied.value) {
      const filters = getFilterParams(props.formValues)
      loadOptions('', { filters })
    }
  }
})

function handleDropdownVisible(visible) {
  if (!visible) return
  if (!bindingSatisfied.value) return
  // dropdown 打开时立即（不防抖）预加载 options，让本地 filterable 有数据可搜
  // 注意：onMounted 时已经预加载，但 dropdown 打开时再保险一次（如 binding 后到时）
  if (optionsList.value.length === 0) {
    const filters = getFilterParams(props.formValues)
    loadOptions('', { filters, pageSize: 200 })
  }
}

function handleRemoteSearch(search) {
  // 远程搜索：用户输入时调用 loadOptions
  if (!bindingSatisfied.value) return
  const filters = getFilterParams(props.formValues)
  loadOptionsDebounced(search, { filters, pageSize: 200 })
}

async function handleSelectChange(val) {
  // 关键：先 await resolveDisplay 获取 display text，然后一起 emit
  // 避免在 formData 变化导致 ValueHelpField 重新挂载后再 emit
  const safeEmit = (event, payload) => {
    if (instance && instance.emit) {
      instance.emit(event, payload)
    } else {
      emit(event, payload)
    }
  }
  // 计算 displayText（不依赖异步）
  let displayText = ''
  if (Array.isArray(val)) {
    displayText = optionsList.value
      .filter(opt => val.includes(opt.value))
      .map(opt => opt.display)
      .join(', ')
  } else {
    const opt = optionsList.value.find(o => o.value === val)
    displayText = opt?.display || ''
    // 同步调用 resolveDisplay 让 optionsList 包含新 option（不 await）
    // 这样即使 VH 被重建，新 VH 也会通过 initial_options 拿到新 display
    if (val != null && val !== '') {
      resolveDisplay(val)
    }
  }
  // 一次 emit 完毕（modelValue + displayValue）
  safeEmit('update:modelValue', val)
  safeEmit('update:displayValue', displayText)
  // 保存到 recent
  if (Array.isArray(val)) {
    val.forEach(v => {
      const opt = optionsList.value.find(o => o.value === v)
      if (opt) saveRecentItem(opt)
    })
  } else {
    const opt = optionsList.value.find(o => o.value === val)
    if (opt) {
      saveRecentItem(opt)
      if (outMappings.value.length > 0) {
        const updates = applyOutMappings(opt, props.formValues)
        if (Object.keys(updates).length > 0) {
          safeEmit('out-mapping', updates)
        }
      }
    }
  }
  safeEmit('change', val)
}

function handleDialogOpen() {
  if (!props.disabled) {
    dialogVisible.value = true
  }
}

function handleDialogConfirm(selection) {
  if (isMultiple.value) {
    const values = selection.map(s => s.value)
    emit('update:modelValue', values)
    emit('update:displayValue', selection.map(s => s.display).join(', '))
    selection.forEach(s => saveRecentItem(s))
    emit('change', values)
  } else {
    const val = selection?.value ?? ''
    emit('update:modelValue', val)
    emit('update:displayValue', selection?.display || '')
    if (selection) saveRecentItem(selection)
    emit('change', val)
    if (selection && outMappings.value.length > 0) {
      const updates = applyOutMappings(selection, props.formValues)
      if (Object.keys(updates).length > 0) {
        emit('out-mapping', updates)
      }
    }
  }
}

function handleAutocomplete(query, cb) {
  const filters = getFilterParams(props.formValues)
  loadOptions(query, { filters }).then(() => {
    cb(optionsList.value.map(opt => ({
      value: opt.display,
      item: opt,
    })))
  })
}

function handleAutocompleteSelect(item) {
  emit('update:modelValue', item.item.value)
  emit('update:displayValue', item.item.display)
  saveRecentItem(item.item)
  emit('change', item.item.value)
  if (item.item && outMappings.value.length > 0) {
    const updates = applyOutMappings(item.item, props.formValues)
    if (Object.keys(updates).length > 0) {
      emit('out-mapping', updates)
    }
  }
}

function handleAutocompleteInput(val) {
  if (!val) {
    emit('update:modelValue', '')
    emit('update:displayValue', '')
    emit('change', '')
  }
}
</script>

<style scoped>
.value-help-field {
  width: 100%;
  min-width: 0;
}
.vh-search-icon {
  cursor: pointer;
}
</style>
