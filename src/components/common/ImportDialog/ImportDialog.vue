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
        <el-step title="执行导入" />
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
              <!-- [FIX 2026-06-16 BMRD] 列顺序调整: sheet → 序号(行号) → 字段 → 值 → 错误信息 -->
              <el-table-column prop="sheet" label="Sheet" width="120" />
              <el-table-column prop="row" label="行号" width="80" />
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

      <!-- 步骤 3: 执行导入（进度展示） -->
      <div v-else-if="currentStep === 2" class="step-content">
        <div class="import-progress">
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
          <p class="import-progress__hint">
            <em>导入完成后将自动展示详细结果</em>
          </p>
        </div>
      </div>

      <!-- 步骤 4: 导入结果（统计 + 失败/告警明细） -->
      <div v-else-if="currentStep === 3" class="step-content">
        <div v-if="importResult" class="import-result">
          <!-- 整体状态摘要 -->
          <el-alert
            v-if="!hasAnyFailure && !hasAnyWarning"
            title="导入成功"
            type="success"
            show-icon
            :closable="false"
          >
            <template #default>
              <p>
                成功导入 <strong>{{ totalSuccessCount }}</strong> 条数据
                （创建 {{ totalCreatedCount }}、更新 {{ totalUpdatedCount }}、删除 {{ totalDeletedCount }}）
              </p>
            </template>
          </el-alert>

          <el-alert
            v-else-if="!hasAnyFailure && hasAnyWarning"
            title="导入完成（存在告警）"
            type="warning"
            show-icon
            :closable="false"
          >
            <template #default>
              <p>
                成功 <strong>{{ totalSuccessCount }}</strong> 条（创建 {{ totalCreatedCount }}、更新 {{ totalUpdatedCount }}、删除 {{ totalDeletedCount }}），
                告警 <strong>{{ totalWarningCount }}</strong> 条
              </p>
            </template>
          </el-alert>

          <el-alert
            v-else
            title="导入完成，但有错误"
            type="error"
            show-icon
            :closable="false"
          >
            <template #default>
              <p>
                成功 <strong>{{ totalSuccessCount }}</strong> 条（创建 {{ totalCreatedCount }}、更新 {{ totalUpdatedCount }}、删除 {{ totalDeletedCount }}），
                失败 <strong>{{ totalFailedCount }}</strong> 条
                <span v-if="totalWarningCount > 0">，告警 {{ totalWarningCount }} 条</span>
              </p>
            </template>
          </el-alert>

          <!-- 统计明细（按对象类型） -->
          <div v-if="importResult.results" class="import-details">
            <h4 class="import-details__title">
              导入结果统计
              <span class="title-hint">（点击"对象类型"可过滤下方失败/告警明细）</span>
            </h4>
            <el-table :data="importResultsTable" size="small" border>
              <el-table-column label="对象类型" min-width="120">
                <template #default="{ row }">
                  <el-link
                    :type="filterType === row.typeId ? 'primary' : 'default'"
                    :underline="false"
                    :disabled="row.failed === 0 && row.warning === 0"
                    class="type-link"
                    @click="handleTypeFilter(row)"
                  >
                    <span v-if="filterType === row.typeId">[已选] </span>{{ row.type }}
                  </el-link>
                </template>
              </el-table-column>
              <el-table-column prop="created" label="创建" width="80" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.created > 0" type="success" size="small">{{ row.created }}</el-tag>
                  <span v-else>-</span>
                </template>
              </el-table-column>
              <el-table-column prop="updated" label="更新" width="80" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.updated > 0" type="primary" size="small">{{ row.updated }}</el-tag>
                  <span v-else>-</span>
                </template>
              </el-table-column>
              <el-table-column prop="deleted" label="删除" width="80" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.deleted > 0" type="info" size="small">{{ row.deleted }}</el-tag>
                  <span v-else>-</span>
                </template>
              </el-table-column>
              <el-table-column prop="skipped" label="跳过" width="80" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.skipped > 0" type="warning" size="small">{{ row.skipped }}</el-tag>
                  <span v-else>-</span>
                </template>
              </el-table-column>
              <el-table-column prop="failed" label="失败" width="80" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.failed > 0" type="danger" size="small">{{ row.failed }}</el-tag>
                  <span v-else>-</span>
                </template>
              </el-table-column>
              <el-table-column prop="warning" label="告警" width="80" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.warning > 0" type="warning" size="small">{{ row.warning }}</el-tag>
                  <span v-else>-</span>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!-- 失败明细 -->
          <div v-if="importResult.errors && importResult.errors.length > 0" class="import-errors">
            <h4 class="import-errors__title">
              失败明细
              <span class="title-hint">（共 {{ importResult.errors.length }} 条{{ filterType ? `，当前显示 ${filteredErrors.length} 条` : '' }}）</span>
            </h4>
            <!-- [NEW v1.2.3 2026-06-17] 过滤状态条 -->
            <div v-if="filterType" class="filter-banner">
              <el-icon><Filter /></el-icon>
              <span>已过滤：<strong>{{ filterTypeName }}</strong> 的失败明细</span>
              <el-button link type="primary" size="small" @click="clearTypeFilter">清除过滤</el-button>
            </div>
            <el-table
              :data="pagedErrors"
              size="small"
              border
              max-height="320"
              row-key="key"
            >
              <!-- [NEW v1.2.3 2026-06-17] 可展开行: 显示完整错误信息 + 原始记录 -->
              <el-table-column type="expand" width="40">
                <template #default="{ row }">
                  <div class="error-detail">
                    <div class="error-detail__section">
                      <div class="error-detail__label">完整错误信息：</div>
                      <div class="error-detail__message">{{ row.message }}</div>
                    </div>
                    <div v-if="row.value" class="error-detail__section">
                      <div class="error-detail__label">字段值：</div>
                      <div class="error-detail__value">{{ row.value }}</div>
                    </div>
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="row" label="行号" width="60" align="center" />
              <el-table-column prop="operation" label="操作" width="70" align="center">
                <template #default="{ row }">
                  <el-tag size="small" :type="operationTagType(row.operation)">{{ operationLabel(row.operation) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="对象类型" width="100" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ getErrorTypeName(row.object_type) }}
                </template>
              </el-table-column>
              <el-table-column prop="field" label="字段" width="80" />
              <el-table-column prop="message" label="错误信息" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">
                  <span class="message-summary">{{ row.message }}</span>
                </template>
              </el-table-column>
            </el-table>
            <el-pagination
              v-model:current-page="errorsCurrentPage"
              v-model:page-size="errorsPageSize"
              :total="filteredErrors.length"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next, jumper"
              small
              class="import-pagination"
            />
          </div>

          <!-- 告警明细 -->
          <div v-if="hasAnyWarning" class="import-warnings">
            <h4 class="import-warnings__title">
              告警明细
              <span class="title-hint">（共 {{ totalWarningCount }} 条{{ filterType ? `，当前显示 ${filteredWarnings.length} 条` : '' }}）</span>
            </h4>
            <el-table
              :data="pagedWarnings"
              size="small"
              border
              max-height="320"
              row-key="key"
            >
              <el-table-column type="expand" width="40">
                <template #default="{ row }">
                  <div class="error-detail">
                    <div class="error-detail__section">
                      <div class="error-detail__label">完整告警信息：</div>
                      <div class="error-detail__message">{{ row.message }}</div>
                    </div>
                    <div v-if="row.value" class="error-detail__section">
                      <div class="error-detail__label">字段值：</div>
                      <div class="error-detail__value">{{ row.value }}</div>
                    </div>
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="row" label="行号" width="60" align="center" />
              <el-table-column prop="operation" label="操作" width="70" align="center">
                <template #default="{ row }">
                  <el-tag size="small" type="warning">{{ operationLabel(row.operation) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="对象类型" width="100" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ getErrorTypeName(row.object_type) }}
                </template>
              </el-table-column>
              <el-table-column prop="field" label="字段" width="80" />
              <el-table-column prop="message" label="告警信息" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">
                  <span class="message-summary">{{ row.message }}</span>
                </template>
              </el-table-column>
            </el-table>
            <el-pagination
              v-model:current-page="warningsCurrentPage"
              v-model:page-size="warningsPageSize"
              :total="filteredWarnings.length"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next, jumper"
              small
              class="import-pagination"
            />
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button v-if="currentStep > 0 && currentStep < 3" @click="prevStep">上一步</el-button>
      <el-button @click="handleClose">{{ currentStep === 3 ? '关闭' : '取消' }}</el-button>
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
        下一步：执行导入
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useCrudMessage } from '@/composables/useCrudMessage'
import { UploadFilled, Download, Filter } from '@element-plus/icons-vue'
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

// [NEW v1.2.3 2026-06-17] 失败/告警明细分页
const errorsPageSize = ref(10)
const errorsCurrentPage = ref(1)
const warningsPageSize = ref(10)
const warningsCurrentPage = ref(1)

// [NEW v1.2.3 2026-06-17] 失败/告警对象类型过滤
// 点击统计表中的对象类型可过滤下方明细
const filterType = ref(null)  // null = 不过滤, 字符串 = object type id

const schema = ref(null)
const loadingSchema = ref(false)

// [NEW v1.2.3 2026-06-17] 对象类型 labels 映射 (id -> 中文名)
// 来自 /api/v1/meta/objects API，props.objectTypeLabels 优先覆盖
const objectTypeLabelsMap = ref({})

// [REMOVED v1.2.12 2026-06-17] cascadeChain: 死代码
// 原用于"选择导入层级" UI (v1.0.0 设计), 已被 sheet-grouped layout 替代
// metaService.buildCascadeChain() 仍保留 (search_help 仍在用), 只在导入流程不再使用

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

// [REMOVED v1.2.12 2026-06-17] selectedCascadeFields: 死代码 (cascadeChain 已删)

const dialogTitle = computed(() => {
  const titles = ['导入数据', '数据校验', '执行导入', '导入结果']
  return titles[currentStep.value] || '导入数据'
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

const failedCount = computed(() => {
  if (!importResult.value?.results) return 0
  let count = 0
  Object.values(importResult.value.results).forEach(r => {
    count += (r.failed || 0)
  })
  return count
})

// [NEW v1.2.3 2026-06-17] 第四步统计 computed
const totalSuccessCount = computed(() => {
  if (!importResult.value?.results) return 0
  return Object.values(importResult.value.results).reduce((sum, r) => sum + (r.success || 0), 0)
})

const totalCreatedCount = computed(() => {
  if (!importResult.value?.results) return 0
  return Object.values(importResult.value.results).reduce((sum, r) => sum + (r.created || 0), 0)
})

const totalUpdatedCount = computed(() => {
  if (!importResult.value?.results) return 0
  return Object.values(importResult.value.results).reduce((sum, r) => sum + (r.updated || 0), 0)
})

const totalDeletedCount = computed(() => {
  if (!importResult.value?.results) return 0
  return Object.values(importResult.value.results).reduce((sum, r) => sum + (r.deleted || 0), 0)
})

const totalFailedCount = computed(() => {
  if (!importResult.value?.results) return 0
  return Object.values(importResult.value.results).reduce((sum, r) => sum + (r.failed || 0), 0)
})

const totalWarningCount = computed(() => {
  if (!importResult.value?.results) return 0
  return Object.values(importResult.value.results).reduce((sum, r) => sum + ((r.warnings || []).length), 0)
})

const hasAnyFailure = computed(() => totalFailedCount.value > 0)
const hasAnyWarning = computed(() => totalWarningCount.value > 0)

// 收集所有 warnings（按对象类型聚合）
const allWarnings = computed(() => {
  if (!importResult.value?.results) return []
  const result = []
  Object.entries(importResult.value.results).forEach(([type, r]) => {
    if (r.warnings && Array.isArray(r.warnings)) {
      r.warnings.forEach(w => result.push({ ...w, object_type: type }))
    }
  })
  return result
})

// [NEW v1.2.3 2026-06-17] 分页数据
const pagedErrors = computed(() => {
  const all = filteredErrors.value
  const start = (errorsCurrentPage.value - 1) * errorsPageSize.value
  return all.slice(start, start + errorsPageSize.value).map((e, i) => ({
    ...e,
    key: `err-${errorsCurrentPage.value}-${i}-${e.row || 0}-${e.object_type || ''}`
  }))
})

const pagedWarnings = computed(() => {
  const all = filteredWarnings.value
  const start = (warningsCurrentPage.value - 1) * warningsPageSize.value
  return all.slice(start, start + warningsPageSize.value).map((w, i) => ({
    ...w,
    key: `warn-${warningsCurrentPage.value}-${i}-${w.row || 0}-${w.object_type || ''}`
  }))
})

// [NEW v1.2.3 2026-06-17] 按对象类型过滤后的 errors / warnings
const filteredErrors = computed(() => {
  const all = importResult.value?.errors || []
  if (!filterType.value) return all
  return all.filter(e => e.object_type === filterType.value)
})

const filteredWarnings = computed(() => {
  if (!filterType.value) return allWarnings.value
  return allWarnings.value.filter(w => w.object_type === filterType.value)
})

// 过滤时自动回到第 1 页
watch(filterType, () => {
  errorsCurrentPage.value = 1
  warningsCurrentPage.value = 1
})

// 过滤模式下显示的类型名
const filterTypeName = computed(() => {
  if (!filterType.value) return ''
  return objectTypeLabelsMap.value?.[filterType.value]
    || props.objectTypeLabels?.[filterType.value]
    || filterType.value
})

// 错误对象类型名称映射 (失败明细)
// 优先用 objectTypeLabelsMap (从 /meta/objects API 加载), props 兜底
const getErrorTypeName = (ot) => {
  return objectTypeLabelsMap.value?.[ot] || props.objectTypeLabels?.[ot] || ot
}

const importResultsTable = computed(() => {
  if (!importResult.value?.results) return []
  return Object.entries(importResult.value.results).map(([type, result]) => {
    // [FIX 2026-06-17] 用 objectTypeLabelsMap 拿中文名，schema.fields 是字段不是对象类型
    const displayName = objectTypeLabelsMap.value?.[type] || props.objectTypeLabels?.[type] || type
    return {
      type: displayName,
      typeId: type,  // 保留 id 用于调试
      created: result.created || 0,
      updated: result.updated || 0,
      deleted: result.deleted || 0,
      skipped: result.skipped || 0,
      failed: result.failed || 0,
      warning: (result.warnings || []).length
    }
  })
})

// 操作模式映射
function operationLabel(op) {
  const map = { create: '新增', update: '更新', delete: '删除', skip: '跳过', upsert: 'upsert' }
  return map[op] || (op || '-')
}

function operationTagType(op) {
  const map = { create: 'success', update: 'primary', delete: 'info', skip: 'warning', upsert: 'primary' }
  return map[op] || ''
}

// [NEW v1.2.3 2026-06-17] 切换对象类型过滤
function handleTypeFilter(row) {
  if (!row?.typeId) return
  // 同一行再次点击 = 取消过滤
  if (filterType.value === row.typeId) {
    filterType.value = null
  } else {
    filterType.value = row.typeId
  }
}

function clearTypeFilter() {
  filterType.value = null
}

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
    const [schemaResult, objectsResult] = await Promise.all([
      metaService.getSchema(props.objectType),
      // [NEW v1.2.3 2026-06-17] 加载所有对象类型 labels 映射
      // /api/v1/meta/objects 返回 [{id, name, ...}]，用于第 4 步显示中文名
      metaService._request('GET', '/meta/objects').catch(() => ({ success: false, data: [] }))
    ])

    if (schemaResult.success && schemaResult.data) {
      schema.value = schemaResult.data
      const importConfig = metaService.getImportExportConfig(schemaResult.data)
      if (importConfig?.conflictStrategy) {
        conflictStrategy.value = importConfig.conflictStrategy
      }
    }

    // 构建 objectTypeLabels 映射
    if (objectsResult.success && Array.isArray(objectsResult.data)) {
      const map = {}
      objectsResult.data.forEach(obj => {
        if (obj?.id) {
          map[obj.id] = obj.name || obj.id
        }
      })
      // 合并 props 传入的 objectTypeLabels (props 优先)
      objectTypeLabelsMap.value = { ...map, ...(props.objectTypeLabels || {}) }
    } else {
      objectTypeLabelsMap.value = { ...(props.objectTypeLabels || {}) }
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
  // [NEW v1.2.3 2026-06-17] 重置分页
  errorsCurrentPage.value = 1
  warningsCurrentPage.value = 1
  // [NEW v1.2.3 2026-06-17] 重置对象类型过滤
  filterType.value = null
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
      // [REMOVED v1.2.12] cascade_fields 死参数, 后端不使用
      // [FIX 2026-06-16 BMRD] preview 也必须传 context (version_id / product_id),
      // 否则后端 validate_sheets 不会跳过 product_code/version_code 必填验证
      version_id: props.context?.version_id,
      product_id: props.context?.product_id
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
  // [FIX v1.2.12 2026-06-17] totalTypes: 多对象模式用选中数, 单对象模式 = 1
  totalTypes.value = props.multiTypeMode ? selectedMultiTypes.value.length : 1

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
        product_id: props.context?.product_id
        // [REMOVED v1.2.12] cascade_fields 死参数
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
          const hasErrors = data.result?.errors?.length > 0
          const resultSuccess = data.result?.success !== false && !hasErrors
          importResult.value = {
            success: resultSuccess,
            results: data.result?.results || {},
            errors: data.result?.errors || []
          }
          importing.value = false
          // [NEW v1.2.3 2026-06-17] 切到第 4 步展示详细结果
          currentStep.value = 3
          if (resultSuccess && successCount.value > 0) {
            message.success(`成功导入 ${successCount.value} 条数据`)
          } else if (hasErrors) {
            message.warning(`导入完成，但有 ${data.result.errors.length} 条错误`)
          }
          // [FIX 2026-06-17] 不在此处 emit success，否则父组件会立刻关闭 dialog
          // 用户在第 4 步点"关闭"按钮时再 emit，让用户先看到完整结果
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
  // [NEW v1.2.3 2026-06-17] 第 4 步点"关闭"时通知父组件导入完成，让父组件刷新列表
  if (currentStep.value === 3 && importResult.value) {
    emit('success', importResult.value)
  }
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

// [REMOVED v1.2.12 2026-06-17] .object-type-selector / .object-type-checkbox
// 死代码: 原用于"选择导入层级" UI, 该 UI 已删除

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
.import-errors,
.import-warnings {
  margin-bottom: var(--spacing-lg);

  &__title {
    margin: 0 0 var(--spacing-sm);
    font-size: var(--el-font-size-base, 14px);
    font-weight: 500;
    color: var(--el-text-color-primary, #303133);
  }
}

// [NEW v1.2.3 2026-06-17] 第四步导入结果样式
.import-errors__title {
  color: var(--el-color-danger, #f56c6c) !important;
}

.import-warnings__title {
  color: var(--el-color-warning, #e6a23c) !important;
}

.title-hint {
  margin-left: var(--spacing-xs);
  font-weight: 400;
  font-size: var(--el-font-size-small, 12px);
  color: var(--el-text-color-secondary, #909399);
}

.import-progress__hint {
  margin-top: var(--spacing-md);
  text-align: center;
  color: var(--el-text-color-secondary, #909399);
  font-size: var(--el-font-size-small, 12px);
}

// [NEW v1.2.3 2026-06-17] 分页
.import-pagination {
  margin-top: var(--spacing-sm);
  justify-content: flex-end;
  display: flex;
}

// [NEW v1.2.3 2026-06-17] 对象类型过滤 - 可点击链接
.type-link {
  font-weight: 500;
  cursor: pointer;
}

// [NEW v1.2.3 2026-06-17] 过滤状态条
.filter-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  margin-bottom: var(--spacing-sm);
  background: var(--el-color-primary-light-9, #ecf5ff);
  border: 1px solid var(--el-color-primary-light-5, #d9ecff);
  border-radius: var(--radius-sm, 4px);
  font-size: var(--el-font-size-base, 14px);
  color: var(--el-text-color-regular, #606266);

  strong {
    color: var(--el-color-primary, #409eff);
    font-weight: 600;
  }

  .el-icon {
    color: var(--el-color-primary, #409eff);
  }
}

// [NEW v1.2.3 2026-06-17] 错误信息展开详情
.error-detail {
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: var(--radius-sm, 4px);
  font-size: var(--el-font-size-small, 13px);

  &__section {
    margin-bottom: var(--spacing-sm);

    &:last-child {
      margin-bottom: 0;
    }
  }

  &__label {
    margin-bottom: var(--spacing-xs);
    font-weight: 500;
    color: var(--el-text-color-regular, #606266);
  }

  &__message {
    padding: var(--spacing-xs) var(--spacing-sm);
    background: var(--el-color-danger-light-9, #fef0f0);
    border-left: 3px solid var(--el-color-danger, #f56c6c);
    color: var(--el-text-color-primary, #303133);
    word-break: break-all;
    white-space: pre-wrap;
    line-height: 1.5;
  }

  &__value {
    padding: var(--spacing-xs) var(--spacing-sm);
    background: var(--el-bg-color, #fff);
    border: 1px solid var(--el-border-color-light, #e4e7ed);
    border-radius: var(--radius-sm, 2px);
    color: var(--el-text-color-primary, #303133);
    word-break: break-all;
    font-family: var(--el-font-family-mono, monospace);
  }
}

.message-summary {
  cursor: pointer;
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
