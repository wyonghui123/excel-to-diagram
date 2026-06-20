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
          <!-- [NEW v1.2.14 2026-06-19] 紧凑顶部摘要: 一行展示 alert + 统计条 -->
          <div class="preview-summary">
            <el-alert
              v-if="!hasValidationErrors"
              title="数据校验通过"
              type="success"
              show-icon
              :closable="false"
              class="preview-summary__alert"
            >
              <template #default>
                <span>共 <strong>{{ totalPreviewRows }}</strong> 条数据可以导入</span>
              </template>
            </el-alert>
            <el-alert
              v-else
              :title="`数据校验发现问题（${errorCount} 条）`"
              type="warning"
              show-icon
              :closable="false"
              class="preview-summary__alert"
            />

            <!-- [NEW v1.2.13 2026-06-19] Step 2 总览统计条 (紧凑 inline) -->
            <div class="overview-strip overview-strip--inline overview-strip--compact">
              <div class="overview-strip__item overview-strip__item--primary">
                <span class="overview-strip__value overview-strip__value--primary">{{ totalPreviewRows }}</span>
                <span class="overview-strip__label">总行数</span>
              </div>
              <div class="overview-strip__item" :class="previewSheetsCount > 0 ? 'overview-strip__item--info' : ''">
                <span class="overview-strip__value" :class="previewSheetsCount > 0 ? 'overview-strip__value--info' : ''">{{ previewSheetsCount }}</span>
                <span class="overview-strip__label">数据表数</span>
              </div>
              <div class="overview-strip__item" :class="errorCount > 0 ? 'overview-strip__item--danger' : ''">
                <span class="overview-strip__value" :class="errorCount > 0 ? 'overview-strip__value--danger' : ''">{{ errorCount }}</span>
                <span class="overview-strip__label">错误数</span>
              </div>
              <div class="overview-strip__item" :class="previewWarningCount > 0 ? 'overview-strip__item--warning' : ''">
                <span class="overview-strip__value" :class="previewWarningCount > 0 ? 'overview-strip__value--warning' : ''">{{ previewWarningCount }}</span>
                <span class="overview-strip__label">告警数</span>
              </div>
            </div>
          </div>

          <!-- [NEW v1.2.12 2026-06-19] Step 2 Sheet 折叠面板 (按对象类型分组) -->
          <div v-if="previewResult.sheets && previewResult.sheets.length > 0" class="preview-sheets">
            <h4 class="sheets-info__title">按数据表查看问题：</h4>
            <el-collapse v-model="activePreviewSheets" class="sheet-collapse-list">
              <el-collapse-item
                v-for="sheet in previewSheetGroups"
                :key="sheet.name"
                :name="sheet.name"
                class="sheet-collapse"
              >
                <template #title>
                  <div class="sheet-collapse__header">
                    <span class="sheet-collapse__title">{{ sheet.name }}</span>
                    <span class="sheet-collapse__tags">
                      <el-tag v-if="sheet.errorCount > 0" type="danger" size="small">{{ sheet.errorCount }} 错</el-tag>
                      <el-tag v-if="sheet.warningCount > 0" type="warning" size="small">{{ sheet.warningCount }} 警</el-tag>
                      <el-tag size="small" type="info">{{ sheet.rowCount }} 行</el-tag>
                    </span>
                  </div>
                </template>
                <div class="sheet-collapse__content">
                  <el-tabs v-model="sheet.activeTab" class="sheet-tabs">
                    <el-tab-pane label="错误" name="errors">
                      <el-table
                        v-if="sheet.errors.length > 0"
                        :data="sheet.errors"
                        size="small"
                        border
                        max-height="300"
                      >
                        <el-table-column prop="row" label="行号" width="80" align="center" />
                        <el-table-column prop="field" label="字段" width="120" />
                        <el-table-column prop="value" label="值" width="120" show-overflow-tooltip />
                        <el-table-column prop="message" label="错误信息" min-width="200" show-overflow-tooltip />
                      </el-table>
                      <p v-else class="tip">无错误</p>
                    </el-tab-pane>
                    <el-tab-pane label="告警" name="warnings">
                      <el-table
                        v-if="sheet.warnings.length > 0"
                        :data="sheet.warnings"
                        size="small"
                        border
                        max-height="300"
                      >
                        <el-table-column prop="row" label="行号" width="80" align="center" />
                        <el-table-column prop="field" label="字段" width="120" />
                        <el-table-column prop="value" label="值" width="120" show-overflow-tooltip />
                        <el-table-column prop="message" label="告警信息" min-width="200" show-overflow-tooltip />
                      </el-table>
                      <p v-else class="tip">无告警</p>
                    </el-tab-pane>
                  </el-tabs>
                </div>
              </el-collapse-item>
            </el-collapse>
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
          <!-- [NEW v1.2.14 2026-06-19] 紧凑顶部摘要: alert + 6 列统计条 一行展示 -->
          <div class="import-summary">
            <el-alert
              v-if="!hasAnyFailure && !hasAnyWarning"
              :title="`导入成功（${totalSuccessCount} 条）`"
              type="success"
              show-icon
              :closable="false"
              class="import-summary__alert"
            >
              <template #default>
                <span>创建 <strong>{{ totalCreatedCount }}</strong>、更新 <strong>{{ totalUpdatedCount }}</strong>、删除 <strong>{{ totalDeletedCount }}</strong></span>
              </template>
            </el-alert>

            <el-alert
              v-else-if="!hasAnyFailure && hasAnyWarning"
              :title="`导入完成（存在 ${totalWarningCount} 条告警）`"
              type="warning"
              show-icon
              :closable="false"
              class="import-summary__alert"
            />

            <el-alert
              v-else
              :title="`导入完成，但有 ${totalFailedCount} 条错误`"
              type="error"
              show-icon
              :closable="false"
              class="import-summary__alert"
            />

            <!-- [NEW v1.2.13 2026-06-19] Step 4 总览统计条 (紧凑 inline 6 列) -->
            <div class="overview-strip overview-strip--inline overview-strip--compact overview-strip--result">
              <div class="overview-strip__item overview-strip__item--success">
                <span class="overview-strip__value overview-strip__value--success">{{ totalCreatedCount }}</span>
                <span class="overview-strip__label">创建</span>
              </div>
              <div class="overview-strip__item overview-strip__item--primary">
                <span class="overview-strip__value overview-strip__value--primary">{{ totalUpdatedCount }}</span>
                <span class="overview-strip__label">更新</span>
              </div>
              <div class="overview-strip__item overview-strip__item--info">
                <span class="overview-strip__value overview-strip__value--info">{{ totalDeletedCount }}</span>
                <span class="overview-strip__label">删除</span>
              </div>
              <div class="overview-strip__item" :class="totalSkippedCount > 0 ? 'overview-strip__item--warning' : ''">
                <span class="overview-strip__value" :class="totalSkippedCount > 0 ? 'overview-strip__value--warning' : ''">{{ totalSkippedCount }}</span>
                <span class="overview-strip__label">跳过</span>
              </div>
              <div class="overview-strip__item" :class="totalFailedCount > 0 ? 'overview-strip__item--danger' : ''">
                <span class="overview-strip__value" :class="totalFailedCount > 0 ? 'overview-strip__value--danger' : ''">{{ totalFailedCount }}</span>
                <span class="overview-strip__label">失败</span>
              </div>
              <div class="overview-strip__item" :class="totalWarningCount > 0 ? 'overview-strip__item--orange' : ''">
                <span class="overview-strip__value" :class="totalWarningCount > 0 ? 'overview-strip__value--orange' : ''">{{ totalWarningCount }}</span>
                <span class="overview-strip__label">告警</span>
              </div>
            </div>
          </div>

          <!-- [NEW v1.2.12 2026-06-19] 级联失败 banner (business_object 失败时显示) -->
          <div v-if="hasCascadeFailure" class="cascade-failure-banner" data-testid="cascade-banner">
            <div class="cascade-failure-banner__title">
              <el-icon><Warning /></el-icon>
              <span>检测到级联失败</span>
            </div>
            <div class="cascade-failure-banner__detail">
              主对象类型 <strong>{{ cascadeRootTypeName }}</strong> 有 {{ cascadeRootFailed }} 条导入失败，
              导致依赖它的 <strong>{{ cascadeDependentCount }}</strong> 个下游对象类型全部失败
              （共 <strong>{{ cascadeDependentFailed }}</strong> 条）。请先修复主对象类型的失败原因。
            </div>
          </div>

          <!-- [NEW v1.2.12 2026-06-19] Step 4 Sheet 折叠面板 (按对象类型分) -->
          <div v-if="importResult.results && Object.keys(importResult.results).length > 0" class="import-sheets">
            <h4 class="sheets-info__title">按对象类型查看：</h4>
            <el-collapse v-model="activeImportSheets" class="sheet-collapse-list">
              <el-collapse-item
                v-for="row in importResultsTable"
                :key="row.typeId"
                :name="row.typeId"
                class="sheet-collapse"
              >
                <template #title>
                  <div class="sheet-collapse__header">
                    <span class="sheet-collapse__title">{{ row.type }}</span>
                    <span class="sheet-collapse__tags">
                      <el-tag v-if="row.failed > 0" type="danger" size="small">{{ row.failed }} 失败</el-tag>
                      <el-tag v-if="row.warning > 0" type="warning" size="small">{{ row.warning }} 告警</el-tag>
                      <el-tag v-if="row.skipped > 0" type="info" size="small">{{ row.skipped }} 跳过</el-tag>
                    </span>
                  </div>
                </template>
                <div class="sheet-collapse__content">
                  <el-tabs v-model="row.activeTab" class="sheet-tabs">
                    <el-tab-pane :label="`成功 (${row.successCount})`" name="success">
                      <el-table
                        v-if="getTypeSuccesses(row.typeId).length > 0"
                        :data="getTypeSuccesses(row.typeId)"
                        size="small"
                        border
                        max-height="300"
                        row-key="row"
                      >
                        <el-table-column prop="row" label="行号" width="60" align="center" />
                        <el-table-column prop="operation" label="操作" width="70" align="center">
                          <template #default="{ row: okRow }">
                            <el-tag size="small" :type="operationTagType(okRow.operation)">{{ operationLabel(okRow.operation) }}</el-tag>
                          </template>
                        </el-table-column>
                        <el-table-column prop="code" label="业务编码" width="160" show-overflow-tooltip />
                        <el-table-column prop="name" label="名称" min-width="200" show-overflow-tooltip />
                      </el-table>
                      <p v-else class="tip">无成功记录</p>
                    </el-tab-pane>
                    <el-tab-pane :label="`失败 (${row.failed})`" name="errors">
                      <el-table
                        v-if="getTypeErrors(row.typeId).length > 0"
                        :data="getTypeErrors(row.typeId)"
                        size="small"
                        border
                        max-height="300"
                        row-key="row"
                      >
                        <el-table-column type="expand" width="40">
                          <template #default="{ row: errRow }">
                            <div class="error-detail">
                              <div class="error-detail__section">
                                <div class="error-detail__label">完整错误信息：</div>
                                <div class="error-detail__message">{{ errRow.message }}</div>
                              </div>
                            </div>
                          </template>
                        </el-table-column>
                        <el-table-column prop="row" label="行号" width="60" align="center" />
                        <el-table-column prop="operation" label="操作" width="70" align="center">
                          <template #default="{ row: errRow }">
                            <el-tag size="small" :type="operationTagType(errRow.operation)">{{ operationLabel(errRow.operation) }}</el-tag>
                          </template>
                        </el-table-column>
                        <el-table-column prop="field" label="字段" width="100" />
                        <el-table-column prop="message" label="错误信息" min-width="220" show-overflow-tooltip>
                          <template #default="{ row: errRow }">
                            <span class="message-summary">{{ errRow.message }}</span>
                          </template>
                        </el-table-column>
                      </el-table>
                      <p v-else class="tip">无失败记录</p>
                    </el-tab-pane>
                    <el-tab-pane :label="`告警 (${row.warning})`" name="warnings">
                      <el-table
                        v-if="getTypeWarnings(row.typeId).length > 0"
                        :data="getTypeWarnings(row.typeId)"
                        size="small"
                        border
                        max-height="300"
                        row-key="row"
                      >
                        <el-table-column prop="row" label="行号" width="60" align="center" />
                        <el-table-column prop="operation" label="操作" width="70" align="center">
                          <template #default="{ row: warnRow }">
                            <el-tag size="small" type="warning">{{ operationLabel(warnRow.operation) }}</el-tag>
                          </template>
                        </el-table-column>
                        <el-table-column prop="field" label="字段" width="100" />
                        <el-table-column prop="message" label="告警信息" min-width="220" show-overflow-tooltip>
                          <template #default="{ row: warnRow }">
                            <span class="message-summary">{{ warnRow.message }}</span>
                          </template>
                        </el-table-column>
                      </el-table>
                      <p v-else class="tip">无告警</p>
                    </el-tab-pane>
                    <el-tab-pane :label="`跳过 (${row.skipped})`" name="skipped">
                      <el-table
                        v-if="getTypeSkipped(row.typeId).length > 0"
                        :data="getTypeSkipped(row.typeId)"
                        size="small"
                        border
                        max-height="300"
                        row-key="row"
                      >
                        <el-table-column prop="row" label="行号" width="60" align="center" />
                        <el-table-column prop="operation" label="操作" width="70" align="center">
                          <template #default="{ row: skipRow }">
                            <el-tag size="small" type="info">{{ operationLabel(skipRow.operation) }}</el-tag>
                          </template>
                        </el-table-column>
                        <el-table-column prop="code" label="业务编码" width="160" show-overflow-tooltip />
                        <el-table-column prop="name" label="名称" min-width="200" show-overflow-tooltip />
                      </el-table>
                      <p v-else class="tip">无跳过记录</p>
                    </el-tab-pane>
                  </el-tabs>
                </div>
              </el-collapse-item>
            </el-collapse>
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
// [NEW v1.2.12 2026-06-19] Warning icon: 级联失败 banner
import { UploadFilled, Download, Filter, Warning } from '@element-plus/icons-vue'
import { boService } from '@/services/boService'
import { metaService } from '@/services/metaService'
import { objectTypeService } from '@/services/objectTypeService'

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
  },
  // [NEW v3.20 2026-06-19] 触发菜单编码 (arch-data → 模板走"架构数据"前缀)
  menuCode: {
    type: String,
    default: ''
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

// [NEW v1.2.12 2026-06-19] Sheet 折叠面板: 默认展开第一个有问题的 sheet
const activePreviewSheets = ref([])
const activeImportSheets = ref([])

const schema = ref(null)
const loadingSchema = ref(false)

// [NEW v1.2.3 2026-06-17] 对象类型 labels 映射 (id -> 中文名)
// 来自 /api/v1/meta/objects API，props.objectTypeLabels 优先覆盖
const objectTypeLabelsMap = ref({})

// [REMOVED v1.2.12 2026-06-17] cascadeChain: 死代码
// 原用于"选择导入层级" UI (v1.0.0 设计), 已被 sheet-grouped layout 替代
// metaService.buildCascadeChain() 仍保留 (search_help 仍在用), 只在导入流程不再使用

const availableMultiTypes = computed(() => {
  // [FIX v1.2.18 2026-06-20] 优先用 objectTypeLabelsMap (从 /meta/objects API 加载的中文名),
  // 兼容 props.objectTypeLabels (父组件传入), 最后 fallback 到 type id
  // 否则 annotation 等类型会显示原始 id 而不是 "备注信息"
  return props.objectTypes
    .filter(t => t && typeof t === 'string')
    .map(t => ({
      value: t,
      label: objectTypeLabelsMap.value?.[t] || props.objectTypeLabels?.[t] || t
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
  // [FIX v1.2.18h 2026-06-20] 按 props.objectTypes 顺序排序 (hierarchy 顺序),
  // 而不是依赖 Object.entries 的字典序 (annotation 会排在第一, 颠倒顺序)
  const typeOrder = props.objectTypes || []
  const ordered = []
  // 先按 props.objectTypes 顺序填入
  for (const t of typeOrder) {
    if (importResult.value.results[t]) {
      ordered.push([t, importResult.value.results[t]])
    }
  }
  // 再填入未在 typeOrder 里的 (防御)
  for (const [t, r] of Object.entries(importResult.value.results)) {
    if (!typeOrder.includes(t)) {
      ordered.push([t, r])
    }
  }
  return ordered.map(([type, result]) => {
    // [FIX 2026-06-17] 用 objectTypeLabelsMap 拿中文名，schema.fields 是字段不是对象类型
    const displayName = objectTypeLabelsMap.value?.[type] || props.objectTypeLabels?.[type] || type
    // [FIX v1.2.18 2026-06-20] 成功数 = created + updated + deleted + skipped (移除独立 skip tab)
    const successCount = (result.created || 0) + (result.updated || 0) + (result.deleted || 0) + (result.skipped || 0)
    return {
      type: displayName,
      typeId: type,  // 保留 id 用于调试
      created: result.created || 0,
      updated: result.updated || 0,
      deleted: result.deleted || 0,
      skipped: result.skipped || 0,
      failed: result.failed || 0,
      successCount,
      warning: (result.warnings || []).length,
      // [FIX v1.2.18] 默认 tab: 优先失败 > 成功(含跳过) > 告警
      activeTab: (result.failed || 0) > 0 ? 'errors' : (successCount > 0 ? 'success' : (((result.warnings || []).length > 0) ? 'warnings' : 'success'))
    }
  })
})

// [NEW v1.2.12 2026-06-19] Step 2: 数据表数
const previewSheetsCount = computed(() => {
  return previewResult.value?.sheets?.length || 0
})

// [NEW v1.2.12 2026-06-19] Step 2: 告警数 (从 previewResult.validation.warnings 提取)
const previewWarningCount = computed(() => {
  const warnings = previewResult.value?.validation?.warnings ||
                    previewResult.value?.warnings ||
                    []
  return warnings.length
})

// [NEW v1.2.12 2026-06-19] Step 2: 按 Sheet 分组 (每个 sheet 含 errors/warnings 列表)
const previewSheetGroups = computed(() => {
  const sheets = previewResult.value?.sheets || []
  const allErrors = previewResult.value?.validation?.errors ||
                    previewResult.value?.errors ||
                    []
  const allWarnings = previewResult.value?.validation?.warnings ||
                      previewResult.value?.warnings ||
                      []
  // [FIX v1.2.18h 2026-06-20] 按 props.objectTypes (hierarchy 顺序) 排序 sheets,
  // 保证与 Excel sheet 顺序一致: domain → sub_domain → service_module → business_object → relationship → annotation
  const typeOrder = props.objectTypes || []
  const ordered = []
  for (const t of typeOrder) {
    const s = sheets.find(sheet => sheet.object_type === t)
    if (s) ordered.push(s)
  }
  for (const s of sheets) {
    if (!ordered.includes(s)) ordered.push(s)
  }
  return ordered.map(sheet => {
    const name = sheet.name || sheet.sheet || '-'
    const errors = allErrors.filter(e => (e.sheet || e.table) === name)
    const warnings = allWarnings.filter(w => (w.sheet || w.table) === name)
    return {
      name,
      rowCount: sheet.row_count || sheet.rows || 0,
      errorCount: errors.length,
      warningCount: warnings.length,
      errors: errors.map((err, i) => ({
        row: err.row || err.line || i + 1,
        // [FIX v1.2.18f] 操作模式字段 (来自后端 validation errors[].operation)
        operation: err.operation || '-',
        field: err.field || err.column || '-',
        value: err.value || err.input || '-',
        message: err.error || err.message || String(err)
      })),
      warnings: warnings.map((warn, i) => ({
        row: warn.row || warn.line || i + 1,
        operation: warn.operation || '-',
        field: warn.field || warn.column || '-',
        value: warn.value || warn.input || '-',
        message: warn.error || warn.message || String(warn)
      })),
      activeTab: errors.length > 0 ? 'errors' : (warnings.length > 0 ? 'warnings' : 'errors')
    }
  })
})

// [NEW v1.2.12 2026-06-19] Step 4: 跳过数 (累计)
const totalSkippedCount = computed(() => {
  if (!importResult.value?.results) return 0
  return Object.values(importResult.value.results).reduce((sum, r) => sum + (r.skipped || 0), 0)
})

// [NEW v1.2.12 2026-06-19] Step 4: 级联失败检测
// 场景: business_object 失败时, downstream (relationship/annotation) 也会失败
const hasCascadeFailure = computed(() => {
  const results = importResult.value?.results
  if (!results) return false
  const root = results.business_object
  if (!root || (root.failed || 0) === 0) return false
  // 检查下游对象类型 (relationship / annotation) 是否也全部失败
  const downstream = ['relationship', 'annotation']
  const failedDownstream = downstream.filter(t => {
    const r = results[t]
    return r && (r.failed || 0) > 0
  })
  return failedDownstream.length > 0
})

const cascadeRootTypeName = computed(() => {
  return objectTypeLabelsMap.value?.business_object || props.objectTypeLabels?.business_object || 'business_object'
})

const cascadeRootFailed = computed(() => {
  return importResult.value?.results?.business_object?.failed || 0
})

const cascadeDependentCount = computed(() => {
  const results = importResult.value?.results
  if (!results) return 0
  return ['relationship', 'annotation'].filter(t => {
    const r = results[t]
    return r && (r.failed || 0) > 0
  }).length
})

const cascadeDependentFailed = computed(() => {
  const results = importResult.value?.results
  if (!results) return 0
  return ['relationship', 'annotation'].reduce((sum, t) => {
    const r = results[t]
    return sum + (r?.failed || 0)
  }, 0)
})

// [NEW v1.2.12 2026-06-19] Step 4: 按对象类型获取 errors/warnings
function getTypeErrors(typeId) {
  return (importResult.value?.errors || []).filter(e => e.object_type === typeId)
}

function getTypeWarnings(typeId) {
  return allWarnings.value.filter(w => w.object_type === typeId)
}

// [NEW v1.2.13 2026-06-19] Step 4: 按对象类型获取成功/跳过的明细
// 成功 = created + updated + deleted (不包括 skipped)
const allSuccesses = computed(() => {
  if (!importResult.value?.results) return []
  const result = []
  Object.entries(importResult.value.results).forEach(([type, r]) => {
    // 从 importResult.successes 收集 (后端如果有)
    if (r.successes && Array.isArray(r.successes)) {
      r.successes.forEach(s => result.push({ ...s, object_type: type }))
    }
    // 或者从 errors/successes 区分
  })
  // 兜底: 如果没有 successes 列表, 不显示具体行
  return result
})

const allSkipped = computed(() => {
  if (!importResult.value?.results) return []
  const result = []
  Object.entries(importResult.value.results).forEach(([type, r]) => {
    if (r.skipped_items && Array.isArray(r.skipped_items)) {
      r.skipped_items.forEach(s => result.push({ ...s, object_type: type }))
    }
  })
  return result
})

function getTypeSuccesses(typeId) {
  return allSuccesses.value.filter(s => s.object_type === typeId)
}

function getTypeSkipped(typeId) {
  return allSkipped.value.filter(s => s.object_type === typeId)
}

// [NEW v1.2.12 2026-06-19] 默认展开第一个有问题的 sheet
watch(previewSheetGroups, (groups) => {
  if (groups.length > 0 && activePreviewSheets.value.length === 0) {
    const first = groups.find(g => g.errorCount > 0 || g.warningCount > 0) || groups[0]
    activePreviewSheets.value = [first.name]
  }
}, { immediate: true })

watch(importResultsTable, (rows) => {
  if (rows.length > 0 && activeImportSheets.value.length === 0) {
    const first = rows.find(r => r.failed > 0 || r.warning > 0) || rows[0]
    activeImportSheets.value = [first.typeId]
  }
}, { immediate: true })

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
    const [schemaResult, labelsMap] = await Promise.all([
      metaService.getSchema(props.objectType),
      // [FIX v1.2.18k 2026-06-20] 用 objectTypeService (apiV1 /meta/objects) 取中文名
      // metaService._request 默认走 v2，/meta/objects 只在 v1 注册，会 404。
      objectTypeService.init().catch(() => ({}))
    ])

    if (schemaResult.success && schemaResult.data) {
      schema.value = schemaResult.data
      const importConfig = metaService.getImportExportConfig(schemaResult.data)
      if (importConfig?.conflictStrategy) {
        conflictStrategy.value = importConfig.conflictStrategy
      }
    }

    // 合并 API labels + props 传入的 objectTypeLabels (props 优先)
    objectTypeLabelsMap.value = { ...(labelsMap || {}), ...(props.objectTypeLabels || {}) }
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
    const result = await boService.downloadTemplate(types[0], {
      selected_types: types,
      menu_code: props.menuCode || undefined,
    })
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

.preview-result > .el-alert,
.import-result > .el-alert {
  margin-bottom: var(--spacing-lg);
}

// [NEW v1.2.14 2026-06-19] 紧凑顶部摘要: alert + 统计条 一行展示
.preview-summary,
.import-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--el-fill-color-blank, #fff);
  border: 1px solid var(--el-border-color-light, #e4e7ed);
  border-radius: var(--radius-sm, 4px);

  &__alert {
    flex: 1 1 auto;
    min-width: 200px;
    margin-bottom: 0 !important;
    padding: 4px var(--spacing-sm);

    :deep(.el-alert__content) {
      padding: 0 var(--spacing-xs);
    }

    :deep(.el-alert__title) {
      font-size: var(--el-font-size-base, 14px);
    }
  }
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

// [NEW v1.2.12 2026-06-19] 步骤标题不换行 (dialog 宽度不够时强制换行)
:deep(.el-step__title) {
  white-space: nowrap;
  font-size: var(--el-font-size-base, 14px);
}

// [NEW v1.2.13 2026-06-19] 总览统计条 - 紧凑 inline 布局
.overview-strip {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
  margin-bottom: var(--spacing-md);
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--el-fill-color-blank, #fff);
  border: 1px solid var(--el-border-color-light, #e4e7ed);
  border-radius: var(--radius-sm, 4px);

  &--result {
    // 6 列场景, 允许换行但保持紧凑
  }

  &--inline {
    .overview-strip__item {
      flex-direction: row;
      gap: var(--spacing-xs);
      padding: 2px 8px;
    }
    .overview-strip__value {
      font-size: 14px;
      font-weight: 600;
    }
    .overview-strip__label {
      margin-top: 0;
      font-size: var(--el-font-size-small, 12px);
    }
  }

  &__item {
    display: inline-flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2px 8px;
    border-radius: var(--radius-sm, 4px);
    text-align: center;
    transition: all 0.2s;

    &--success { background: var(--el-color-success-light-9, #f0f9eb); }
    &--primary { background: var(--el-color-primary-light-9, #ecf5ff); }
    &--info    { background: var(--el-color-info-light-9, #f4f4f5); }
    &--warning { background: var(--el-color-warning-light-9, #fdf6ec); }
    &--danger  { background: var(--el-color-danger-light-9, #fef0f0); }
    &--orange  { background: rgba(234, 88, 12, 0.08); }
  }

  &__value {
    font-size: 14px;
    font-weight: 600;
    line-height: 1.2;

    &--success { color: var(--el-color-success, #67c23a); }
    &--primary { color: var(--el-color-primary, #409eff); }
    &--info    { color: var(--el-color-info, #909399); }
    &--warning { color: var(--el-color-warning, #e6a23c); }
    &--danger  { color: var(--el-color-danger, #f56c6c); }
    &--orange  { color: var(--yonyou-orange-600, #ea580c); }
  }

  &__label {
    margin-top: 0;
    font-size: var(--el-font-size-small, 12px);
    color: var(--el-text-color-secondary, #909399);
  }
}

// [NEW v1.2.12 2026-06-19] Sheet 折叠面板 (按对象类型分)
.sheet-collapse {
  margin-bottom: var(--spacing-md);

  &__header {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
    width: 100%;
  }

  &__title {
    font-size: var(--el-font-size-base, 14px);
    font-weight: 500;
    color: var(--el-text-color-primary, #303133);
  }

  &__tags {
    display: inline-flex;
    gap: var(--spacing-xs);
  }

  &__count {
    font-size: var(--el-font-size-small, 12px);
    color: var(--el-text-color-secondary, #909399);
  }

  &__content {
    padding: var(--spacing-sm) 0;
  }
}

// [NEW v1.2.12 2026-06-19] Sheet 内 tab 容器 (Error/Warning 分离)
.sheet-tabs {
  :deep(.el-tabs__header) {
    margin: 0 0 var(--spacing-sm) 0;
  }
}

// [NEW v1.2.12 2026-06-19] 级联失败 banner
.cascade-failure-banner {
  margin-bottom: var(--spacing-md);
  padding: var(--spacing-md);
  background: rgba(230, 162, 60, 0.1);
  border: 1px solid rgba(230, 162, 60, 0.4);
  border-left: 4px solid var(--el-color-warning, #e6a23c);
  border-radius: var(--radius-sm, 4px);
  color: var(--el-text-color-primary, #303133);

  &__title {
    display: flex;
    align-items: center;
    gap: var(--spacing-xs);
    font-weight: 600;
    color: var(--el-color-warning, #b88230);
    margin-bottom: var(--spacing-xs);
  }

  &__detail {
    font-size: var(--el-font-size-small, 13px);
    line-height: 1.5;
    color: var(--el-text-color-regular, #606266);
  }
}

// [NEW v1.2.12 2026-06-19] Stats 标签页 - 4 列统计网格
.import-stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-md);
  padding: var(--spacing-md);

  &__item {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: var(--spacing-md);
    background: var(--el-fill-color-light, #f5f7fa);
    border-radius: var(--radius-sm, 4px);
  }

  &__label {
    font-size: var(--el-font-size-small, 12px);
    color: var(--el-text-color-secondary, #909399);
    margin-bottom: var(--spacing-xs);
  }

  &__value {
    font-size: 24px;
    font-weight: 600;
    line-height: 1;
  }
}

.more-errors {
  margin-top: var(--spacing-xs);
  color: var(--el-text-color-secondary, #909399);
  font-size: var(--el-font-size-small, 12px);
}
</style>
