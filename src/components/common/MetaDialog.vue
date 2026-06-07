<template>
  <AppModal
      :model-value="visible"
      :title="dialogTitle"
      :width="width"
      :z-index="zIndex"
      @close="handleClose"
    >
    <MetaForm
      v-if="visible"
      ref="formRef"
      key="meta-form"
      :fields="metaFields"
      :model-value="initialFormData"
      :layout="formLayout"
      :label-position="labelPosition"
      :field-policy="fieldPolicy"
      @update:model-value="handleDataChange"
    >
      <template v-for="field in slotFields" :key="field.key" #[`field-${field.key}`]="scope">
        <slot :name="`field-${field.key}`" v-bind="scope" />
      </template>
    </MetaForm>

    <template #footer>
      <AppButton variant="secondary" @click="handleClose">{{ cancelText }}</AppButton>
      <AppButton variant="primary" :loading="saving" @click="handleSave">{{ confirmText }}</AppButton>
    </template>
  </AppModal>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import AppModal from './AppModal/AppModal.vue'
import AppButton from './AppButton/AppButton.vue'
import MetaForm from './MetaForm.vue'
import { useFieldPolicy } from '@/composables/useFieldPolicy'  // [DECORATIVE] [NEW] v1.3 / FR-6.7

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  meta: {
    type: Object,
    required: true,
    validator: (val) => val.fields && Array.isArray(val.fields)
  },
  entityData: {
    type: Object,
    default: null
  },
  title: {
    type: String,
    default: ''
  },
  addTitle: {
    type: String,
    default: '新增'
  },
  editTitle: {
    type: String,
    default: '编辑'
  },
  width: {
    type: String,
    default: '520px'
  },
  formLayout: {
    type: String,
    default: 'vertical'
  },
  labelPosition: {
    type: String,
    default: 'top'
  },
  confirmText: {
    type: String,
    default: '保存'
  },
  cancelText: {
    type: String,
    default: '取消'
  },
  saving: {
        type: Boolean,
        default: false
      },
      zIndex: {
        type: [String, Number],
        default: null
      }
    })

const emit = defineEmits(['close', 'save', 'update:entityData', 'update:visible'])

const formRef = ref(null)
const formData = ref({})

const metaFields = computed(() => props.meta.fields || [])

// [DECORATIVE] [NEW] v1.3 / FR-6.7: 字段策略（必须在 metaFields 定义之后）
const { isRequiredByRow, requiredMap } = useFieldPolicy(
  computed(() => props.meta),
  computed(() => metaFields.value)
)

const fieldPolicy = computed(() => ({
  isRequiredByRow,
  requiredMap
}))

const slotFields = computed(() => metaFields.value.filter(f => f.slot))

const dialogTitle = computed(() => {
  if (props.title) return props.title
  const label = props.meta.label || props.meta.name || ''
  return props.entityData ? `${props.editTitle}${label}` : `${props.addTitle}${label}`
})

const initialFormData = computed(() => {
  if (!props.entityData) {
    const data = {}
    metaFields.value.forEach(f => {
      data[f.key] = f.defaultValue ?? (f.type === 'checkbox' || f.type === 'switch' ? false : '')
    })
    return data
  }
  const data = { ...props.entityData }
  metaFields.value.forEach(f => {
    const rawValue = props.entityData[f.key]
    if (f.type === 'checkbox' || f.type === 'switch') {
      data[f.key] = rawValue ? true : false
    } else if (rawValue === undefined || rawValue === null) {
      data[f.key] = f.defaultValue ?? ''
    }
  })
  return data
})

watch(() => props.visible, (val) => {
  if (!val) {
    formData.value = {}
  }
})

function handleDataChange(data) {
  formData.value = data
}

async function handleClose() {
  emit('update:visible', false)
  emit('close')
}

async function handleSave() {
  if (!formRef.value) return
  const valid = formRef.value.validateAll()
  if (!valid) return
  emit('save', formRef.value.getFormData())
}

defineExpose({
  getFormData: () => formRef.value?.getFormData(),
  validateAll: () => formRef.value?.validateAll(),
  resetForm: () => formRef.value?.resetForm(),
  setFormData: (data) => formRef.value?.setFormData(data),
  formRef
})
</script>

<style scoped lang="scss">
</style>
