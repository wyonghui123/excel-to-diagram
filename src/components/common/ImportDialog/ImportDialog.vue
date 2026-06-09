<template>
  <el-dialog
    :model-value="visible"
    :title="dialogTitle"
    width="680px"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:visible', $event)"
    @close="handleClose"
  >
    <div class="import-dialog-content">
      <el-steps :active="currentStep" finish-status="success" simple style="margin-bottom: 20px;">
        <el-step title="选择文件" />
        <el-step title="数据校验" />
        <el-step title="导入结果" />
      </el-steps>

      <!-- 步骤 1: 选择文件 -->
      <div v-if="currentStep === 0" class="step-content">
        <!-- 多类型导入模式：选择导入对象 -->
        <div v-if="multiTypeMode && availableMultiTypes.length > 0" class="multi-type-section">
          <div class="multi-type-section__label">选择导入对象</div>
          <div class="multi-type-section__items">
            <label
              v-for="item in availableMultiTypes"
              :key="item.value"
              class="multi-type-checkbox"
            >
              <input type="checkbox" v-model="selectedMultiTypes" :value="item.value" />
              <span>{{ item.label }}</span>
            </label>
          </div>
        </div>

        <!-- 单类型导入信息 -->
        <div v-else class="import-info">
          <p>导入 <strong>{{ objectTypeName }}</strong> 数据</p>
          <p class="tip">请选择要导入的 Excel 文件，系统将自动校验数据格式</p>
        </div>

        <!-- 多对象类型选择（从元数据驱动，仅单对象模式） -->
        <div v-if="!multiTypeMode && cascadeChain.length > 1" class="object-type-selector">
          <div class="object-type-selector__label">选择导入层级</div>
          <div class="object-type-selector__items">
            <el-checkbox
              v-for="item in cascadeChain"
              :key="item.field"
              v-model="item.selected"
              :disabled="item.level === 1"
              class="object-type-checkbox"
            >
              {{ item.label }}
              <span v-if="item.parentLabel" class="cascade-hint">← 依赖 {{ item.parentLabel }}</span>
            </el-checkbox>
          </div>
        </div>

        <el-form label-width="100px">
          <el-form-item label="上传文件">
            <el-upload
              ref="uploadRef"
              :auto-upload="false"
              :limit="1"
              accept=".xlsx,.xls"
              :on-change="handleFileChange"
              :on-remove="handleFileRemove"
              :file-list="fileList"
              drag
            >
              <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
              <div class="el-upload__text">
                拖拽文件到此处，或 <em>点击选择文件</em>
              </div>
              <template #tip>
                <div class="el-upload__tip">
                  支持 .xlsx 和 .xls 格式文件
                </div>
              </template>
            </el-upload>
          </el-form-item>

          <el-form-item label="冲突处理">
            <el-radio-group v-model="conflictStrategy">
              <el-radio label="upsert">更新已存在的记录</el-radio>
              <el-radio label="skip">跳过已存在的记录</el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item label="模板下载">
            <el-button type="primary" link @click="downloadTemplate">
              <el-icon><Download /></el-icon>
              {{ multiTypeMode ? '下载全局导入模板' : `下载 ${objectTypeName} 导入模板` }}
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- 步骤 2: 预览确认 -->
      <div v-else-if="currentStep === 1" class="step-content">
        <div v-if="previewing" class="loading-container">
          <el-progress
            :percentage="previewProgress.percent"
            :stroke-width="8"
            :color="progressColor"
          />
          <p class="loading-text">{{ previewProgress.message }}</p>
        </div>

        <div v-else-if="previewResult" class="preview-result">
          <el-alert
            v-if="!hasValidationErrors"
            title="数据校验通过"
            type="success"
            show-icon
            :closable="false"
          >
            <template #default>
              <p>共发现 <strong>{{ totalPreviewRows }}</strong> 条数据可以导入</p>
            </template>
          </el-alert>

          <el-alert
            v-else
            title="数据校验发现问题"
            type="warning"
            show-icon
            :closable="false"
          >
            <template #default>
              <p>共 {{ totalPreviewRows }} 条数据，其中 {{ errorCount }} 条存在问题</p>
            </template>
          </el-alert>

          <div v-if="previewResult.sheets && previewResult.sheets.length > 0" class="sheets-info">
            <h4 class="sheets-info__title">检测到的数据表：</h4>
            <el-table :data="previewResult.sheets" size="small" border>
              <el-table-column prop="name" label="Sheet名称" />
              <el-table-column label="数据行数" width="100">
                <template #default="{ row }">
                  {{ row.row_count || row.rows || 0 }}
                </template>
              </el-table-column>
              <el-table-column label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.hasErrors ? 'warning' : 'success'" size="small">
                    {{ row.hasErrors ? '有错误' : '有效' }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <div v-if="hasValidationErrors" class="validation-errors">
            <h4 class="validation-errors__title">校验错误详情：</h4>
            <el-table :data="validationErrors" size="small" border max-height="300">
              <el-table-column prop="row" label="行号" width="80" />
              <el-table-column prop="sheet" label="Sheet" width="100" />
              <el-table-column prop="field" label="字段" width="120" />
              <el-table-column prop="value" label="值" width="120" show-overflow-tooltip />
              <el-table-column prop="message" label="错误信息" min-width="200" show-overflow-tooltip />
            </el-table>
            <p v-if="errorCount > 20" class="more-errors">
              还有 {{ errorCount - 20 }} 条错误未显示...
            </p>
          </div>
        </div>
      </div>

      <!-- 步骤 3: 导入结果 -->
      <div v-else-if="currentStep === 2" class="step-content">
        <div v-if="importing" class="import-progress">
          <el-progress
            :percentage="importProgress"
            :stroke-width="10"
            :color="progressColor"
          />
          <p class="import-progress__type" v-if="currentTypeName">
            正在导入 <strong>{{ currentTypeName }}</strong> ({{ currentIndex }}/{{ totalTypes }})
          </p>
          <p class="import-progress__percent">
            已完成 {{ importProgress }}%
          </p>
        </div>

        <div v-else-if="importResult" class="import-result">
          <el-alert
            v-if="importResult.success"
            title="导入成功"
            type="success"
            show-icon
            :closable="false"
          >
            <template #default>
              <p>成功导入 <strong>{{ successCount }}</strong> 条数据</p>
            </template>
          </el-alert>

          <el-alert
            v-else
            title="导入完成，但有错误"
            type="warning"
            show-icon
            :closable="false"
          >
            <template #default>
              <p>成功 {{ successCount }} 条，失败 {{ importResult.errors?.length || 0 }} 条</p>
            </template>
          </el-alert>

          <div v-if="importResult.results" class="import-details">
            <h4 class="import-details__title">导入详情：</h4>
            <el-table :data="importResultsTable" size="small" border>
              <el-table-column prop="type" label="对象类型" />
              <el-table-column prop="created" label="新增" width="80" align="center">
                <template #default="{ row }">
                  <span class="count-created">{{ row.created }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="updated" label="更新" width="80" align="center">
                <template #default="{ row }">
                  <span class="count-updated">{{ row.updated }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="skipped" label="跳过" width="80" align="center">
                <template #default="{ row }">
                  <span class="count-skipped">{{ row.skipped }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="failed" label="失败" width="80" align="center">
                <template #default="{ row }">
                  <span class="count-failed">{{ row.failed }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <div v-if="importResult.errors && importResult.errors.length > 0" class="import-errors">
            <h4 class="import-errors__title">错误详情：</h4>
            <el-table :data="importResult.errors.slice(0, 10)" size="small" border max-height="200">
              <el-table-column prop="row" label="行号" width="80" align="center" />
              <el-table-column prop="message" label="错误信息" />
            </el-table>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button v-if="currentStep > 0 && !importing" @click="prevStep">上一步</el-button>
      <el-button @click="handleClose">{{ currentStep === 2 ? '关闭' : '取消' }}</el-button>
      <el-button
        v-if="currentStep === 0"
        type="primary"
        :disabled="!selectedFile"
        @click="startPreview"
      >
        下一步：校验数据
      </el-button>
      <el-button
        v-if="currentStep === 1 && previewResult"
        type="primary"
        :disabled="!canImport"
        @click="startImport"
      >
        确认导入
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useCrudMessage } from '@/composables/useCrudMessage'
import { UploadFilled, Download } from '@element-plus/icons-vue'
import { boService } from '@/services/boService'
import { metaService } from '@/services/metaService'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  objectType: {
    type: String,
    required: true
  },
  objectTypes: {
    type: Array,
    default: () => []
  },
  objectTypeLabels: {
    type: Object,
    default: () => ({})
  },
  multiTypeMode: {
    type: Boolean,
    default: false
  },
  context: {
    type: Object,
    default: () => ({})
  },
  fields: {
    type: Array,
    default: () => []
  },
  importOptions: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['update:visible', 'success', 'close'])

const message = useCrudMessage()

const uploadRef = ref(null)
const currentStep = ref(0)
const selectedFile = ref(null)
const fileList = ref([])
const conflictStrategy = ref('upsert')

const previewing = ref(false)
const previewResult = ref(null)
const previewProgress = ref({ percent: 0, message: '正在解析文件...' })

const importing = ref(false)
const importResult = ref(null)
const importProgress = ref(0)
const currentTypeName = ref('')
const currentIndex = ref(0)
const totalTypes = ref(0)

const schema = ref(null)
const loadingSchema = ref(false)

const cascadeChain = computed(() => {
  if (!schema.value) return []

  const chain = metaService.buildCascadeChain(schema.value)

  return chain.map(item => ({
    ...item,
    selected: item.cascadeLevel > 1
  }))
})

const availableMultiTypes = computed(() => {
  return props.objectTypes
    .filter(t => t && typeof t === 'string')
    .map(t => ({
      value: t,
      label: props.objectTypeLabels[t] || t
    }))
})

const selectedMultiTypes = ref([])

const objectTypeName = computed(() => {
  if (!schema.value) return props.objectType

  const fields = schema.value.fields || []
  const field = fields.find(f => f.id === props.objectType)
  return field?.name || schema.value.name || props.objectType
})

const selectedCascadeFields = computed(() => {
  return cascadeChain.value
    .filter(item => item.selected)
    .map(item => item.field)
})

const dialogTitle = computed(() => {
  const titles = ['导入数据', '数据校验', '导入结果']
  return titles[currentStep.value]
})

const totalPreviewRows = computed(() => {
  if (!previewResult.value?.sheets) return 0
  return previewResult.value.sheets.reduce((sum, sheet) => sum + (sheet.row_count || sheet.rows || 0), 0)
})

const errorCount = computed(() => {
  const errors = previewResult.value?.validation?.errors ||
                  previewResult.value?.errors ||
                  []
  return errors.length
})

const hasValidationErrors = computed(() => errorCount.value > 0)

const validationErrors = computed(() => {
  const errors = previewResult.value?.validation?.errors ||
                  previewResult.value?.errors ||
                  []
  return errors.slice(0, 20).map((err, index) => ({
    row: err.row || err.line || index + 1,
    sheet: err.sheet || err.table || '-',
    field: err.field || err.column || '-',
    value: err.value || err.input || '-',
    message: err.error || err.message || String(err)
  }))
})

const canImport = computed(() => {
  return previewResult.value && totalPreviewRows.value > 0
})

const successCount = computed(() => {
  if (!importResult.value?.results) return 0
  let count = 0
  Object.values(importResult.value.results).forEach(r => {
    count += (r.success || r.created || r.updated || 0)
  })
  return count
})

const importResultsTable = computed(() => {
  if (!importResult.value?.results) return []
  return Object.entries(importResult.value.results).map(([type, result]) => {
    const field = schema.value?.fields?.find(f => f.id === type)
    return {
      type: field?.name || type,
      created: result.created || result.success || 0,
      updated: result.updated || 0,
      skipped: result.skipped || 0,
      failed: result.failed || 0
    }
  })
})

const progressColor = computed(() => {
  if (importProgress.value < 50) return 'var(--yonyou-orange-600, #ea580c)'
  if (importProgress.value < 80) return 'var(--el-color-warning, #e6a23c)'
  return 'var(--el-color-success, #67c23a)'
})

watch(() => props.visible, (newVal) => {
  if (newVal) {
    resetState()
    loadSchema()
  }
})

onMounted(() => {
  if (props.visible) {
    loadSchema()
  }
})

async function loadSchema() {
  if (schema.value || loadingSchema.value) return

  loadingSchema.value = true
  try {
    const result = await metaService.getSchema(props.objectType)
    if (result.success && result.data) {
      schema.value = result.data
      const importConfig = metaService.getImportExportConfig(result.data)
      if (importConfig?.conflictStrategy) {
        conflictStrategy.value = importConfig.conflictStrategy
      }
    }
  } catch (e) {
    console.error('[ImportDialog] 加载 schema 失败:', e)
  } finally {
    loadingSchema.value = false
  }
}

function resetState() {
  currentStep.value = 0
  selectedFile.value = null
  fileList.value = []
  selectedMultiTypes.value = props.objectTypes.filter(t => t && typeof t === 'string')
  previewing.value = false
  previewResult.value = null
  previewProgress.value = { percent: 0, message: '正在解析文件...' }
  importing.value = false
  importResult.value = null
  importProgress.value = 0
  currentTypeName.value = ''
  currentIndex.value = 0
  totalTypes.value = 0
}

function handleFileChange(file) {
  selectedFile.value = file.raw
  fileList.value = [file]
}

function handleFileRemove() {
  selectedFile.value = null
  fileList.value = []
}

function prevStep() {
  if (currentStep.value > 0) {
    currentStep.value--
  }
}

async function startPreview() {
  if (!selectedFile.value) {
    message.warning('请选择要导入的文件')
    return
  }

  currentStep.value = 1
  previewing.value = true
  previewResult.value = null
  previewProgress.value = { percent: 10, message: '正在上传文件...' }

  let progressInterval = setInterval(() => {
    if (previewProgress.value.percent < 90) {
      previewProgress.value.percent = Math.min(90, previewProgress.value.percent + Math.floor(Math.random() * 10 + 2))
      previewProgress.value.message = '正在解析Excel文件...'
    }
  }, 300)

  try {
    const result = await boService.previewImport(props.objectType, selectedFile.value, {
      conflictStrategy: conflictStrategy.value,
      cascade_fields: selectedCascadeFields.value
    })

    clearInterval(progressInterval)
    previewProgress.value.percent = 100
    previewProgress.value.message = '解析完成'

    if (result.success) {
      previewResult.value = result.data
    } else {
      message.error('数据校验失败', result)
      currentStep.value = 0
    }
  } catch (e) {
    clearInterval(progressInterval)
    message.error('数据校验失败: ' + (e.message || '未知错误'), e)
    currentStep.value = 0
  } finally {
    previewing.value = false
  }
}

async function startImport() {
  currentStep.value = 2
  importing.value = true
  importResult.value = null
  importProgress.value = 0
  currentTypeName.value = ''
  currentIndex.value = 0
  totalTypes.value = selectedCascadeFields.value.length

  if (!props.context?.version_id && !props.context?.product_id) {
    message.warning('请先在顶部导航栏选择产品和版本上下文后再导入')
    importing.value = false
    return
  }

  try {
    const response = await boService.importDataAsync(
      selectedFile.value,
      conflictStrategy.value,
      {
        version_id: props.context?.version_id,
        product_id: props.context?.product_id,
        cascade_fields: selectedCascadeFields.value
      }
    )

    if (!response.success || !response.data?.task_id) {
      importResult.value = {
        success: false,
        errors: [{ message: response.message || '启动导入任务失败' }]
      }
      importing.value = false
      return
    }

    const taskId = response.data.task_id
    pollImportProgress(taskId)
  } catch (e) {
    importResult.value = {
      success: false,
      errors: [{ message: e.message || '未知错误' }]
    }
    importing.value = false
  }
}

async function pollImportProgress(taskId) {
  const poll = async () => {
    try {
      const statusRes = await boService.getImportStatus(taskId)

      if (statusRes.success && statusRes.data) {
        const data = statusRes.data
        importProgress.value = data.progress || 0
        currentTypeName.value = data.current_type_name || ''

        const field = schema.value?.fields?.find(f => f.id === data.current_type)
        currentTypeName.value = field?.name || data.current_type_name || ''

        currentIndex.value = data.current_index || 0

        if (data.status === 'completed') {
          importResult.value = {
            success: true,
            results: data.result?.results || {},
            errors: data.result?.errors || []
          }
          importing.value = false
          if (successCount.value > 0) {
            message.success(`成功导入 ${successCount.value} 条数据`)
          }
          emit('success', importResult.value)
        } else if (data.status === 'failed') {
          importResult.value = {
            success: false,
            errors: [{ message: data.error || '导入失败' }]
          }
          importing.value = false
          message.error(data.error || '导入失败')
        } else {
          setTimeout(poll, 1000)
        }
      } else {
        setTimeout(poll, 1000)
      }
    } catch (e) {
      console.error('[ImportDialog] 轮询状态失败:', e)
      setTimeout(poll, 1000)
    }
  }

  poll()
}

async function downloadTemplate() {
  try {
    const { boService } = await import('@/services/boService')
    const types = props.multiTypeMode && selectedMultiTypes.value.length > 0
      ? [...selectedMultiTypes.value]
      : [props.objectType]
    const result = await boService.downloadTemplate(types[0], { selected_types: types })
    if (result.success) {
      message.success('模板下载成功')
    } else {
      message.error('模板下载失败', result)
    }
  } catch (e) {
    message.error('模板下载失败: ' + e.message, e)
  }
}

function handleClose() {
  selectedFile.value = null
  fileList.value = []
  if (uploadRef.value) {
    uploadRef.value.clearFiles()
  }
  emit('update:visible', false)
  emit('close')
}
</script>

<style scoped lang="scss">
@import '@/styles/mixins.scss';

.import-dialog-content {
  padding: var(--spacing-md) 0;
}

.step-content {
  min-height: 200px;
}

.import-info {
  margin-bottom: var(--spacing-lg);

  p {
    margin: 0 0 var(--spacing-xs);
  }

  strong {
    color: var(--yonyou-orange-600, #ea580c);
  }
}

.tip {
  color: var(--el-text-color-secondary, #909399);
  font-size: var(--el-font-size-base, 14px);
}

.multi-type-section {
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-md);
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: var(--radius-md, 6px);

  &__label {
    margin-bottom: var(--spacing-sm);
    font-size: var(--el-font-size-small, 12px);
    font-weight: 500;
    color: var(--el-text-color-regular, #606266);
  }

  &__items {
    display: flex;
    flex-wrap: wrap;
    gap: var(--spacing-sm);
  }
}

.multi-type-checkbox {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--el-bg-color, #fff);
  border-radius: var(--radius-sm, 4px);
  cursor: pointer;
  font-size: var(--el-font-size-base, 14px);

  input[type="checkbox"] {
    margin: 0;
  }
}

.object-type-selector {
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-md);
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: var(--radius-md, 6px);

  &__label {
    margin-bottom: var(--spacing-sm);
    font-size: var(--el-font-size-small, 12px);
    font-weight: 500;
    color: var(--el-text-color-regular, #606266);
  }

  &__items {
    display: flex;
    flex-wrap: wrap;
    gap: var(--spacing-sm);
  }
}

.object-type-checkbox {
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--el-bg-color, #fff);
  border-radius: var(--radius-sm, 4px);

  .cascade-hint {
    margin-left: var(--spacing-xs);
    font-size: var(--el-font-size-small, 12px);
    color: var(--el-text-color-secondary, #909399);
  }
}

.el-upload__tip {
  margin-top: var(--spacing-xs);
  color: var(--el-text-color-secondary, #909399);
  font-size: var(--el-font-size-small, 12px);
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-xl) 0;
}

.loading-text {
  color: var(--el-text-color-secondary, #909399);
  font-size: var(--el-font-size-base, 14px);
}

.preview-result,
.import-result {
  padding: 0;
}

.preview-result .el-alert,
.import-result .el-alert {
  margin-bottom: var(--spacing-lg);
}

.sheets-info,
.import-details,
.import-errors {
  margin-bottom: var(--spacing-lg);

  &__title {
    margin: 0 0 var(--spacing-sm);
    font-size: var(--el-font-size-base, 14px);
    font-weight: 500;
    color: var(--el-text-color-primary, #303133);
  }
}

.validation-errors {
  &__title {
    margin: 0 0 var(--spacing-sm);
    font-size: var(--el-font-size-base, 14px);
    font-weight: 500;
    color: var(--el-text-color-primary, #303133);
  }

  &__more {
    margin-top: var(--spacing-xs);
    color: var(--el-text-color-secondary, #909399);
    font-size: var(--el-font-size-small, 12px);
  }
}

.import-progress {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-xl) 0;

  &__type {
    margin: 0;
    font-size: var(--el-font-size-base, 14px);
    color: var(--el-text-color-primary, #303133);

    strong {
      color: var(--yonyou-orange-600, #ea580c);
    }
  }

  &__percent {
    margin: 0;
    font-size: var(--el-font-size-small, 12px);
    color: var(--el-text-color-secondary, #909399);
  }
}

.count-created {
  color: var(--el-color-success, #67c23a);
  font-weight: 500;
}

.count-updated {
  color: var(--el-color-info, #909399);
  font-weight: 500;
}

.count-skipped {
  color: var(--el-color-warning, #e6a23c);
}

.count-failed {
  color: var(--el-color-danger, #f56c6c);
}

.more-errors {
  margin-top: var(--spacing-xs);
  color: var(--el-text-color-secondary, #909399);
  font-size: var(--el-font-size-small, 12px);
}
</style>
