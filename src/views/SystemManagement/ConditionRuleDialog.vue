<template>
  <AppModal
    :model-value="true"
    :title="isEditMode ? '编辑条件型权限规则' : '添加条件型权限规则'"
    width="720"
    :show-default-footer="false"
    @close="$emit('close')"
  >
    <div class="dialog-body">
      <AppAlert type="info">
        条件型权限通过属性条件匹配资源，新增满足条件的资源自动继承权限，无需手动配置。
      </AppAlert>

      <div class="form-group">
        <label class="form-label">资源类型 <span class="required">*</span></label>
        <AppSelect
          v-model="form.resource_type"
          :options="resourceTypeOptions"
          placeholder="请选择资源类型"
          @change="onResourceTypeChange"
        />
        <!-- FR-005 重复配置警告 -->
        <div v-if="overlapWarnings.length > 0" class="overlap-warning">
          <AppIcon name="alert-triangle" :size="12" />
          <span>Section 1「管理维度」与本规则存在字段重复配置（共 {{ overlapWarnings.length }} 项），将以本规则（Section 3）为准（spec FR-005）</span>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label">权限级别 <span class="required">*</span></label>
        <div class="level-options">
          <AppButton
            v-for="pl in permissionLevels"
            :key="pl.value"
            :variant="form.permission_level === pl.value ? 'primary' : 'secondary'"
            :disabled="form.is_denied"
            size="sm"
            @click="form.permission_level = pl.value"
          >
            {{ pl.label }}
          </AppButton>
        </div>
        <div v-if="form.is_denied" class="level-hint-denied">
          已启用「禁止权限」：权限级别被禁用（禁止权限优先于所有授权）
        </div>
      </div>

      <div class="form-group">
        <label class="checkbox-label denied-row">
          <input
            type="checkbox"
            v-model="form.is_denied"
            @change="onDeniedChange"
          />
          <span class="denied-label">禁止权限</span>
          <span class="denied-hint">（禁止权限优先：禁止权限优先于所有授权，选中后此规则拒绝访问，权限级别无效）</span>
        </label>
      </div>

      <div v-if="form.resource_type" class="form-group">
        <label class="form-label">条件定义 <span class="required">*</span></label>
        
        <div class="condition-tabs">
          <AppButton
            :variant="mode === 'dimension' ? 'primary' : 'secondary'"
            size="sm"
            @click="mode = 'dimension'"
          >管理维度</AppButton>
          <AppButton
            :variant="mode === 'custom' ? 'primary' : 'secondary'"
            size="sm"
            @click="mode = 'custom'"
          >自定义条件</AppButton>
        </div>

          <div v-if="mode === 'dimension'" class="dimension-mode">
            <div v-for="dim in sortedDimensions" :key="dim.code" class="dimension-item">
              <label class="dim-label">
                <input type="checkbox" :checked="isDimSelected(dim.code)" @change="toggleDimension(dim)" />
                <span class="dim-name">{{ dim.name }}</span>
                <span v-if="dim.relation_object" class="dim-meta" title="支持Value Help"><AppIcon name="link" :size="12" /></span>
              </label>
              <div v-if="isDimSelected(dim.code)" class="dim-config">
                <select v-model="dimConfigs[dim.code].operator" @change="onOperatorChange(dim)" class="dim-operator">
                  <option value="=">等于</option>
                  <option value="IN">包含于（多选）</option>
                  <option value="!=">不等于</option>
                </select>
                <div class="dim-value-wrapper">
                  <!-- 单选模式：Tag展示 + Value Help下拉 -->
                  <template v-if="dimConfigs[dim.code].operator !== 'IN'">
                    <div class="single-select-wrapper">
                      <div class="selected-tags" @click="onDimValueFocus(dim)">
                        <span v-if="dimConfigs[dim.code].displayValue" class="value-tag single-tag">
                          {{ dimConfigs[dim.code].displayValue }}
                          <button class="tag-remove" @click.stop="clearSingleValue(dim)">&times;</button>
                        </span>
                        <input 
                          v-model="dimConfigs[dim.code].displayValue"
                          v-if="!dimConfigs[dim.code].displayValue"
                          @focus="onDimValueFocus(dim)"
                          @blur="onDimValueBlur"
                          :placeholder="getValuePlaceholder(dim)" 
                          class="single-select-input"
                        />
                      </div>
                      <!-- Value Help 下拉 -->
                      <div v-if="activeValueHelp === dim.code && valueHelpOptions.length > 0" class="value-help-dropdown">
                        <div class="value-help-search">
                          <input 
                            v-model="valueHelpSearch" 
                            @input="searchValueHelp(dim)"
                            placeholder="搜索..."
                            class="value-help-search-input"
                            @mousedown.stop
                          />
                        </div>
                        <div class="value-help-list">
                          <div 
                            v-for="opt in valueHelpOptions" 
                            :key="opt.id"
                            class="value-help-item"
                            :class="{ selected: String(dimConfigs[dim.code].value) === String(opt.id) }"
                            @mousedown.prevent="selectValueHelp(dim, opt)"
                          >
                            <span class="value-help-checkbox">
                              <AppIcon :name="String(dimConfigs[dim.code].value) === String(opt.id) ? 'check-square' : 'square'" :size="12" />
                            </span>
                            <span class="value-help-name">{{ opt.display_name }}</span>
                            <span v-if="opt.path" class="value-help-path">{{ opt.path }}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </template>
                  
                  <!-- 多选模式：Tag展示 + 多选下拉 -->
                  <template v-else>
                    <div class="multi-select-wrapper">
                      <div class="selected-tags">
                        <span v-for="(tag, idx) in dimConfigs[dim.code].selectedValues" :key="tag.id" class="value-tag">
                          {{ tag.display_name }}
                          <button class="tag-remove" @click="removeTag(dim, idx)">&times;</button>
                        </span>
                        <input 
                          v-model="dimConfigs[dim.code].searchText"
                          @focus="onMultiSelectFocus(dim)"
                          @blur="onDimValueBlur"
                          @input="searchMultiSelect(dim)"
                          :placeholder="getValuePlaceholder(dim)"
                          class="multi-select-input"
                        />
                      </div>
                      <!-- 多选Value Help下拉 -->
                      <div v-if="activeMultiSelect === dim.code && valueHelpOptions.length > 0" class="value-help-dropdown multi-dropdown">
                        <div class="value-help-search">
                          <input 
                            v-model="valueHelpSearch" 
                            @input="searchValueHelp(dim)"
                            placeholder="搜索..."
                            class="value-help-search-input"
                            @mousedown.stop
                          />
                        </div>
                        <div class="value-help-list">
                          <div 
                            v-for="opt in valueHelpOptions" 
                            :key="opt.id"
                            class="value-help-item"
                            :class="{ selected: isValueSelected(dim, opt.id) }"
                            @mousedown.prevent="toggleMultiSelectValue(dim, opt)"
                          >
                            <span class="value-help-checkbox">
                              <AppIcon :name="isValueSelected(dim, opt.id) ? 'check-square' : 'square'" :size="12" />
                            </span>
                            <span class="value-help-name">{{ opt.display_name }}</span>
                            <span v-if="opt.path" class="value-help-path">{{ opt.path }}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </template>
                </div>
              </div>
            </div>
            <div v-if="availableDimensions.length === 0" class="empty-dim">暂无可用管理维度</div>
          </div>

          <div v-if="mode === 'custom'" class="custom-mode">
            <div class="field-help-section">
              <div class="field-help-header" @click="showFieldHelp = !showFieldHelp">
                <span><AppIcon name="clipboard" :size="14" /> 可用字段参考（点击展开）</span>
                <span class="toggle-icon">{{ showFieldHelp ? '▼' : '▶' }}</span>
              </div>
              <div v-if="showFieldHelp" class="field-help-content">
                <div v-if="fieldMetadata.length === 0" class="field-help-empty">加载中...</div>
                <div v-for="field in fieldMetadata" :key="field.id" class="field-help-item" @click="insertField(field)">
                  <span class="field-help-name">{{ field.name }}</span>
                  <span class="field-help-column">{{ field.db_column }}</span>
                  <span class="field-help-type">{{ field.field_type }}</span>
                  <span v-if="field.is_foreign_key" class="field-help-fk" title="外键，支持Value Help"><AppIcon name="link" :size="12" /> {{ field.relation_object }}</span>
                </div>
              </div>
            </div>
            <textarea v-model="customCondition" @input="updateCondition" rows="3" placeholder="如: product_id IN (1, 2, 3) AND domain_type = 'CORE'" class="condition-input"></textarea>
            <div class="condition-hint">
              支持格式：field = value | field IN (v1, v2) | field != value | AND 组合
            </div>
          </div>
        </div>

        <div v-if="form.condition" class="form-group">
          <label>生成的条件表达式</label>
          <div class="condition-preview">
            <code>{{ form.condition }}</code>
          </div>
          <div class="condition-friendly">
            <span class="friendly-label">业务语义：</span>
            <span class="friendly-text">{{ getFriendlyCondition() }}</span>
          </div>
        </div>

        <div class="form-group">
          <label class="checkbox-label">
            <input type="checkbox" v-model="form.inherit_to_children" />
            <span class="option-label">向下继承</span>
            <span class="option-hint">（条件自动覆盖子级资源：例如 BO 的条件会自动应用到所有服务模块、子领域、领域）</span>
          </label>
        </div>

        <div class="form-group">
          <label class="checkbox-label">
            <input type="checkbox" v-model="form.propagate_to_parents" />
            <span class="option-label">向上传播</span>
            <span class="option-hint">（子级权限提供父级只读可见性：例如有"子领域 X"权限的用户能看见 X 所属的"领域"，spec v1.4 FR-009）</span>
          </label>
        </div>

        <div v-if="previewResult" class="preview-section">
          <label>匹配资源预览</label>
          <div class="preview-result">
            <span class="preview-count">匹配 {{ previewResult.count }} 个资源</span>
            <div v-if="previewResult.resources?.length" class="preview-list">
              <span v-for="r in previewResult.resources.slice(0, 10)" :key="r.id" class="preview-item">
                {{ r.name || r.code || `#${r.id}` }}
              </span>
              <span v-if="previewResult.count > 10" class="preview-more">...等 {{ previewResult.count }} 个</span>
            </div>
          </div>
        </div>
      </div>

    <template #footer>
      <AppButton variant="secondary" @click="$emit('close')">取消</AppButton>
      <AppButton
        variant="primary"
        ghost
        :loading="previewing"
        :disabled="!form.condition"
        @click="doPreview"
      >
        {{ previewing ? '预览中...' : '预览匹配' }}
      </AppButton>
      <AppButton
        variant="primary"
        :loading="saving"
        :disabled="!form.condition"
        @click="handleSave"
      >
        {{ saving ? '保存中...' : (isEditMode ? '保存修改' : '确认添加') }}
      </AppButton>
    </template>
  </AppModal>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { useMessage } from '@/composables/useMessage'
import { AppModal, AppButton, AppAlert, AppSelect } from '@/components/common'
import AppIcon from '@/components/common/AppIcon/AppIcon.vue'
import * as permService from '@/services/permissionService'
import {
  buildConditionFromDimensions,
  translateToFriendlyCondition,
  sortDimensionsByHierarchy,
  filterHiddenDimensions,
  parseConditionToDimConfigs as parseCondition,
} from '@/services/conditionExpressionService'

// FR-004 条件型权限的权限级别（3 档，spec v1.4）
const CONDITION_RULE_PERMISSION_LEVELS = [
  { value: 'read',  label: '只读' },
  { value: 'write', label: '可编辑' },
  { value: 'admin', label: '完全管理' },
]
const permissionLevels = CONDITION_RULE_PERMISSION_LEVELS

const props = defineProps({
  roleId: { type: [String, Number], required: true },
  editingRule: { type: Object, default: null },  // 编辑模式时传入的规则
})
const emit = defineEmits(['close', 'saved'])
const message = useMessage()

const resourceTypeOptions = Object.entries(permService.RESOURCE_LABELS)
  .filter(([key]) => ['domain', 'sub_domain', 'service_module', 'business_object'].includes(key))
  .map(([value, label]) => ({ value, label }))

const form = reactive({
  resource_type: '',
  permission_level: 'read',
  is_denied: false,
  condition: '',
  inherit_to_children: true,
  propagate_to_parents: true,
})

const mode = ref('dimension')
const isEditMode = ref(false)  // 是否为编辑模式
const customCondition = ref('')
const dimensions = ref([])
const dimConfigs = reactive({})
const previewResult = ref(null)
const saving = ref(false)
const previewing = ref(false)

// 值ID到名称的映射缓存（用于显示业务名称而非技术ID）
const valueNameMap = reactive({})

// Value Help 状态
const activeValueHelp = ref('')
const activeMultiSelect = ref('')
const valueHelpOptions = ref([])
const valueHelpSearch = ref('')
let valueHelpTimeout = null

// 字段元数据
const fieldMetadata = ref([])
const showFieldHelp = ref(false)

// 隐藏的维度列表（不适合作为业务权限维度）— 统一来源
const HIDDEN_DIMS = permService.HIDDEN_DIMENSIONS

// 基于级联关系的层级排序（父维度在前，子维度在后）
const sortedDimensions = computed(() => {
  if (!form.resource_type) return []
  const dims = filterHiddenDimensions(availableDimensions.value, HIDDEN_DIMS)

  // 构建层级映射
  const dimMap = {}
  dims.forEach(dim => { dimMap[dim.code] = dim })

  // 计算每个维度的层级深度
  const levelMap = {}
  const getDepth = (dimCode, visited = new Set()) => {
    if (visited.has(dimCode)) return 0
    visited.add(dimCode)
    const dim = dimMap[dimCode]
    if (!dim || !dim.cascade_parent) return 0
    if (dimMap[dim.cascade_parent]) {
      return getDepth(dim.cascade_parent, visited) + 1
    }
    return 0
  }
  dims.forEach(dim => { levelMap[dim.code] = getDepth(dim.code) })

  return sortDimensionsByHierarchy(dims, levelMap)
})

const availableDimensions = computed(() => {
  if (!form.resource_type) return []
  return dimensions.value.filter(d => 
    !d.resource_types || d.resource_types.includes(form.resource_type)
  )
})

function isDimSelected(code) {
  return !!dimConfigs[code]
}

function toggleDimension(dim) {
  if (dimConfigs[dim.code]) {
    delete dimConfigs[dim.code]
  } else {
    dimConfigs[dim.code] = { 
      operator: '=', 
      value: '',
      displayValue: '',
      selectedValues: [],
      searchText: ''
    }
  }
  updateCondition()
}

function onOperatorChange(dim) {
  const config = dimConfigs[dim.code]
  if (!config) return
  
  // 切换操作符时清空值
  if (config.operator === 'IN') {
    config.selectedValues = []
    config.value = ''
    config.displayValue = ''
  } else {
    config.selectedValues = []
    config.value = ''
    config.displayValue = ''
  }
  updateCondition()
}

// 处理用户手动输入显示值
function onDisplayValueInput(dim, inputValue) {
  const config = dimConfigs[dim.code]
  if (!config) return
  
  // 用户手动输入时，直接使用输入值作为实际值
  config.displayValue = inputValue
  config.value = inputValue
  updateCondition()
}

function getValuePlaceholder(dim) {
  const config = dimConfigs[dim.code]
  if (!config) return '值'
  if (config.operator === 'IN') {
    return '点击选择多个值...'
  }
  if (dim.cascade_parent) {
    const parentDim = dimensions.value.find(d => d.code === dim.cascade_parent)
    if (parentDim && isDimSelected(dim.cascade_parent)) {
      return `已过滤（基于${parentDim.name}）`
    }
  }
  return '输入值或从列表选择...'
}

function updateCondition() {
  if (mode.value === 'custom') {
    form.condition = customCondition.value
    return
  }

  form.condition = buildConditionFromDimensions(dimConfigs, dimensions.value, 'AND')
}

// 生成用户友好的条件显示文本（使用业务名称而非技术ID）
function getFriendlyCondition() {
  return translateToFriendlyCondition(
    form.condition,
    dimConfigs,
    valueNameMap,
    dimensions.value,
    {
      mode: mode.value,
      customCondition: customCondition.value,
      backendFriendly: isEditMode.value ? props.editingRule?.friendly_condition : null,
    }
  )
}

function onResourceTypeChange() {
  form.condition = ''
  customCondition.value = ''
  previewResult.value = null
  Object.keys(dimConfigs).forEach(k => delete dimConfigs[k])
  fieldMetadata.value = []
  showFieldHelp.value = false
  overlapWarnings.value = []  // 清空旧警告
  loadFieldMetadata()
  // FR-005 重复配置警告（v1.3 已落地 OverlapWarning，本组件接入）
  if (form.resource_type) {
    fetchOverlapWarnings()
  }
}

// FR-005 OverlapWarning: 查询 Section 1 (管理维度) 与本规则（Section 3）的字段重复
const overlapWarnings = ref([])

async function fetchOverlapWarnings() {
  if (!props.roleId || !form.resource_type) return
  try {
    const r = await permService.loadOverlapWarnings(props.roleId, form.resource_type)
    if (r.success) {
      overlapWarnings.value = r.data?.overlaps || r.data?.warnings || []
    }
  } catch (e) {
    console.warn('overlap check failed', e)
  }
}

// FR-009 禁止权优先：勾选 is_denied 时给出 UI 反馈
function onDeniedChange() {
  if (form.is_denied) {
    // 禁止权生效时 propagate_to_parents 无实际意义（拒绝不可能"可见"），但允许保留
    // 仅做一次温和提示
    message.info('已启用禁止权限：匹配的数据将全部被拒绝，此规则优先级最高')
  }
}

// ========== Value Help（单选） ==========

async function onDimValueFocus(dim) {
  if (!dim.relation_object) return
  activeValueHelp.value = dim.code
  valueHelpSearch.value = ''
  await loadValueHelp(dim)
}

// ========== 多选Value Help ==========

async function onMultiSelectFocus(dim) {
  if (!dim.relation_object) return
  activeMultiSelect.value = dim.code
  valueHelpSearch.value = ''
  await loadValueHelp(dim)
}

function searchMultiSelect(dim) {
  const config = dimConfigs[dim.code]
  if (!config) return
  valueHelpSearch.value = config.searchText || ''
  if (valueHelpTimeout) clearTimeout(valueHelpTimeout)
  valueHelpTimeout = setTimeout(() => {
    loadValueHelp(dim, valueHelpSearch.value)
  }, 300)
}

function isValueSelected(dim, valueId) {
  const config = dimConfigs[dim.code]
  if (!config || !config.selectedValues) return false
  return config.selectedValues.some(v => String(v.id) === String(valueId))
}

function toggleMultiSelectValue(dim, opt) {
  const config = dimConfigs[dim.code]
  if (!config) return

  const idx = config.selectedValues.findIndex(v => String(v.id) === String(opt.id))
  if (idx >= 0) {
    config.selectedValues.splice(idx, 1)
  } else {
    config.selectedValues.push({ id: opt.id, display_name: opt.display_name })
    // 缓存ID到名称的映射
    valueNameMap[`${dim.code}_${opt.id}`] = opt.display_name
  }
  updateCondition()
  
  // 级联刷新：如果有子维度已选中或展开，刷新子维度的选项列表
  refreshChildDimensions(dim)
}

function removeTag(dim, idx) {
  const config = dimConfigs[dim.code]
  if (!config) return
  config.selectedValues.splice(idx, 1)
  updateCondition()
  
  // 级联刷新：刷新子维度的选项列表
  refreshChildDimensions(dim)
}

// 级联刷新子维度
function refreshChildDimensions(parentDim) {
  const childDims = dimensions.value.filter(d => d.cascade_parent === parentDim.code)
  for (const childDim of childDims) {
    if (dimConfigs[childDim.code]) {
      // 如果子维度的下拉正在展开，自动刷新其选项列表
      if (activeMultiSelect.value === childDim.code || activeValueHelp.value === childDim.code) {
        loadValueHelp(childDim).then(() => {
          console.log(`[Cascade] Refreshed ${childDim.name} options based on ${parentDim.name} selection change`)
        })
      }
    }
  }
}

function onDimValueBlur() {
  setTimeout(() => {
    activeValueHelp.value = ''
    activeMultiSelect.value = ''
    valueHelpOptions.value = []
  }, 200)
}

async function loadValueHelp(dim, search = '') {
  try {
    const params = { limit: '50' }
    if (search) params.search = search

    // 如果有父维度且已选中，添加级联过滤
    if (dim.cascade_parent) {
      const parentConfig = dimConfigs[dim.cascade_parent]
      if (parentConfig) {
        const parentDim = dimensions.value.find(d => d.code === dim.cascade_parent)
        if (parentDim) {
          const isMultiSelect = parentConfig.operator === 'IN'

          if (isMultiSelect && parentConfig.selectedValues?.length > 0) {
            const selectedIds = parentConfig.selectedValues.map(v => v.id).join(',')
            params[`filter_${parentDim.field}`] = selectedIds
            params.filter_mode = 'in'
          } else if (parentConfig.value) {
            params[`filter_${parentDim.field}`] = parentConfig.value
          }
        }
      }
    }

    const r = await permService.loadDimensionValues(dim.code, params)
    if (r.success) {
      valueHelpOptions.value = r.data || []
    }
  } catch (e) {
    console.error('Failed to load value help:', e)
  }
}

function searchValueHelp(dim) {
  if (valueHelpTimeout) clearTimeout(valueHelpTimeout)
  valueHelpTimeout = setTimeout(() => {
    loadValueHelp(dim, valueHelpSearch.value)
  }, 300)
}

function selectValueHelp(dim, opt) {
  const config = dimConfigs[dim.code]
  if (!config) return

  // 存储ID作为实际值，同时存储显示名称
  config.value = String(opt.id)
  config.displayValue = opt.display_name
  // 缓存ID到名称的映射
  valueNameMap[`${dim.code}_${opt.id}`] = opt.display_name
  updateCondition()
  activeValueHelp.value = ''
  valueHelpOptions.value = []
  
  // 级联刷新：如果有子维度已选中或展开，清空并刷新子维度的值
  const childDims = dimensions.value.filter(d => d.cascade_parent === dim.code)
  for (const childDim of childDims) {
    if (dimConfigs[childDim.code]) {
      // 清空子维度的值
      dimConfigs[childDim.code].value = ''
      dimConfigs[childDim.code].displayValue = ''
      dimConfigs[childDim.code].selectedValues = []
      
      // 如果子维度的下拉正在展开，自动刷新其选项列表
      if (activeMultiSelect.value === childDim.code || activeValueHelp.value === childDim.code) {
        loadValueHelp(childDim).then(() => {
          console.log(`[Cascade] Refreshed ${childDim.name} options based on ${dim.name}=${opt.display_name}`)
        })
      }
    }
  }
}

function clearSingleValue(dim) {
  const config = dimConfigs[dim.code]
  if (!config) return
  
  config.value = ''
  config.displayValue = ''
  updateCondition()
  
  // 级联刷新：如果有子维度已选中，清空子维度的值（因为父维度被清除）
  const childDims = dimensions.value.filter(d => d.cascade_parent === dim.code)
  for (const childDim of childDims) {
    if (dimConfigs[childDim.code]) {
      dimConfigs[childDim.code].value = ''
      dimConfigs[childDim.code].displayValue = ''
      dimConfigs[childDim.code].selectedValues = []
    }
  }
}

// ========== 字段元数据 ==========

async function loadFieldMetadata() {
  if (!form.resource_type) return
  try {
    const r = await permService.loadFieldMetadata(form.resource_type)
    if (r.success) {
      fieldMetadata.value = r.data || []
    }
  } catch (e) {
    console.error('Failed to load field metadata:', e)
  }
}

function insertField(field) {
  const current = customCondition.value
  const fieldRef = field.db_column
  if (current) {
    customCondition.value = current + ' ' + fieldRef
  } else {
    customCondition.value = fieldRef
  }
  updateCondition()
}

async function doPreview() {
  if (!form.condition || !form.resource_type) return
  previewing.value = true
  try {
    const r = await permService.previewCondition({
      condition: form.condition,
      resource_type: form.resource_type,
    })
    if (r.success) {
      previewResult.value = r.data
    } else {
      message.error(r.message || '预览规则失败，请稍后重试')
    }
  } catch (e) {
    message.error('预览规则失败，请检查网络后重试', e)
  } finally {
    previewing.value = false
  }
}

async function handleSave() {
  if (!form.condition) return
  saving.value = true
  try {
    const r = await permService.saveConditionRule({
      role_id: props.roleId,
      resource_type: form.resource_type,
      condition: form.condition,
      permission_level: form.permission_level,
      is_denied: form.is_denied,
      inherit_to_children: form.inherit_to_children,
      propagate_to_parents: form.propagate_to_parents,
    })
    if (r.success) {
      message.success('权限规则添加成功')
      emit('saved')
      emit('close')
    } else {
      message.error(r.message || '添加权限规则失败，请稍后重试')
    }
  } catch (e) {
    message.error('添加权限规则失败，请检查网络后重试', e)
  } finally {
    saving.value = false
  }
}

async function loadDimensions() {
  try {
    const r = await permService.loadDimensions()
    if (r.success) {
      dimensions.value = r.data?.dimensions || []
    }
  } catch (e) {
    console.error('Failed to load dimensions:', e)
  }
}

onMounted(() => {
  loadDimensions()
  
  // 编辑模式：预填充表单数据
  if (props.editingRule) {
    const rule = props.editingRule
    form.resource_type = rule.resource_type || ''
    form.permission_level = rule.permission_level || 'read'
    form.is_denied = rule.is_denied || false
    form.condition = rule.condition || ''
    form.inherit_to_children = rule.inherit_to_children !== false
    form.propagate_to_parents = rule.propagate_to_parents !== false
    
    isEditMode.value = true
    
    if (form.resource_type) {
      loadFieldMetadata()
    }
    
    // 解析条件表达式，反向填充维度选择器
    if (rule.condition) {
      nextTick(() => parseConditionToDimConfigs(rule.condition))
    }
  }
})

function parseConditionToDimConfigs(condition) {
  if (!condition) return

  const { matched, unmatched } = parseCondition(condition, dimensions.value)

  for (const [code, config] of Object.entries(matched)) {
    if (!dimConfigs[code]) {
      dimConfigs[code] = {
        operator: config.operator,
        value: '',
        displayValue: '',
        selectedValues: [],
        searchText: '',
      }
    }

    const dim = dimensions.value.find(d => d.code === code)
    const dc = dimConfigs[code]
    dc.operator = config.operator

    if (config.operator === 'IN') {
      dc.selectedValues = config.selectedValues
      dc.value = config.value
      if (dim) loadValueHelpForEdit(dim, config.selectedValues.map(v => v.id))
    } else {
      dc.value = config.value
      dc.displayValue = config.displayValue
      if (dim?.relation_object) {
        loadSingleValueHelpForEdit(dim, config.value)
      }
    }
  }

  if (unmatched) {
    mode.value = 'custom'
    form.custom_condition = condition
  }
}

async function loadValueHelpForEdit(dim, ids) {
  try {
    const params = { limit: '100' }
    if (dim.cascade_parent) {
      const parentConfig = dimConfigs[dim.cascade_parent]
      if (parentConfig && parentConfig.value) {
        const parentDim = dimensions.value.find(d => d.code === dim.cascade_parent)
        if (parentDim) {
          params[`filter_${parentDim.field}`] = parentConfig.value
        }
      }
    }

    const r = await permService.loadDimensionValues(dim.code, params)
    if (r.success) {
      const options = r.data || []
      const optionMap = {}
      options.forEach(opt => {
        optionMap[String(opt.id)] = opt.display_name
        optionMap[opt.id] = opt.display_name
      })

      const currentConfig = dimConfigs[dim.code]
      if (!currentConfig) return
      const selectedValues = currentConfig.selectedValues || []
      selectedValues.forEach(sv => {
        const svIdStr = String(sv.id)
        const name = optionMap[svIdStr] || optionMap[sv.id] || sv.display_name || sv.id
        sv.display_name = name
        valueNameMap[`${dim.code}_${svIdStr}`] = name
        valueNameMap[`${dim.code}_${sv.id}`] = name
      })
    }
  } catch (e) {
    console.warn('Failed to load value help for edit:', e)
  }
}

async function loadSingleValueHelpForEdit(dim, valueId) {
  try {
    const r = await permService.loadDimensionValues(dim.code, { limit: '50' })
    if (r.success) {
      const opt = (r.data || []).find(o => String(o.id) === String(valueId))
      if (opt) {
        dimConfigs[dim.code].displayValue = opt.display_name
        valueNameMap[`${dim.code}_${valueId}`] = opt.display_name
      }
    }
  } catch (e) {
    console.warn('Failed to load single value help for edit:', e)
  }
}
</script>

<style scoped>
.dialog-body {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.form-group { display: flex; flex-direction: column; gap: var(--spacing-xs); }
.form-label { font-size: var(--font-size-sm); font-weight: var(--font-weight-medium); color: var(--color-text-secondary); }
.required { color: var(--color-error); }

.level-options { display: flex; gap: var(--spacing-sm); }

.checkbox-label { display: flex; align-items: center; gap: var(--spacing-sm); font-weight: normal !important; cursor: pointer; }
.checkbox-label input[type="checkbox"] { width: 16px; height: 16px; accent-color: var(--color-primary); }
.denied-label { color: var(--color-error); font-weight: var(--font-weight-medium); }
.denied-hint { font-size: var(--font-size-xs); color: var(--color-text-quaternary); }

.option-label { color: var(--color-text-primary); font-weight: var(--font-weight-medium); }
.option-hint { font-size: var(--font-size-xs); color: var(--color-text-quaternary); }

.level-hint-denied {
  font-size: var(--font-size-xs);
  color: var(--color-warning, #d97706);
  background: rgba(217, 119, 6, 0.06);
  border: 1px solid rgba(217, 119, 6, 0.2);
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  margin-top: 2px;
}

.overlap-warning {
  display: flex; align-items: center; gap: 6px;
  font-size: var(--font-size-xs);
  color: var(--color-warning, #d97706);
  background: rgba(217, 119, 6, 0.06);
  border: 1px solid rgba(217, 119, 6, 0.2);
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  margin-top: 4px;
}

.condition-tabs { display: flex; gap: var(--spacing-xs); margin-bottom: var(--spacing-sm); }

.dimension-item { margin-bottom: var(--spacing-sm); }
.dim-label { display: flex; align-items: center; gap: var(--spacing-sm); cursor: pointer; font-weight: normal !important; }
.dim-name { font-size: var(--font-size-sm); color: var(--color-text-primary); }
.dim-field { font-size: var(--font-size-xs); color: var(--color-text-tertiary); font-family: monospace; }
.dim-meta { font-size: var(--font-size-xs); margin-left: auto; }
.dim-config { display: flex; gap: var(--spacing-sm); margin-top: var(--spacing-xs); padding-left: 28px; }
.dim-operator { width: 110px; }
.dim-value { flex: 1; }
.empty-dim { color: var(--color-text-quaternary); font-size: var(--font-size-sm); text-align: center; padding: var(--spacing-md); }

/* Value Help */
.dim-value-wrapper { position: relative; flex: 1; }
.value-help-dropdown {
  position: absolute; top: 100%; left: 0; right: 0;
  background: var(--color-bg-container);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  z-index: 100;
  max-height: 280px;
  overflow-y: auto;
  margin-top: 2px;
}
.value-help-dropdown.multi-dropdown { max-height: 320px; }
.value-help-search {
  padding: var(--spacing-xs) var(--spacing-sm);
  border-bottom: 1px solid var(--color-border);
  position: sticky; top: 0; background: var(--color-bg-container);
}
.value-help-search-input {
  width: 100%;
  padding: var(--spacing-xs) var(--spacing-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
}
.value-help-list { padding: var(--spacing-xs) 0; }
.value-help-item {
  display: flex; align-items: center; gap: var(--spacing-sm);
  padding: var(--spacing-xs) var(--spacing-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
}
.value-help-item:hover { background: var(--color-primary-bg); }
.value-help-item.selected { background: var(--color-primary-bg-subtle); }
.value-help-checkbox { font-size: var(--font-size-sm); color: var(--color-primary); width: 20px; }
.value-help-id { color: var(--color-text-tertiary); font-size: var(--font-size-xs); font-family: monospace; }
.value-help-name { color: var(--color-text-primary); }
.value-help-path { color: var(--color-text-quaternary); font-size: var(--font-size-xs); margin-left: auto; }

/* 多选Tag */
.multi-select-wrapper { position: relative; flex: 1; }
.single-select-wrapper { position: relative; flex: 1; }
.selected-tags {
  display: flex; flex-wrap: wrap; align-items: center; gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-container);
  min-height: 36px;
  cursor: pointer;
}
.selected-tags:hover { border-color: var(--color-primary); }
.value-tag {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 8px;
  background: var(--color-primary-bg);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  color: var(--color-primary);
}
.single-tag { cursor: default; }
.tag-remove {
  border: none; background: transparent; color: var(--color-primary);
  cursor: pointer; font-size: 14px; padding: 0; line-height: 1;
}
.tag-remove:hover { color: var(--color-error); }
.multi-select-input, .single-select-input {
  border: none; background: transparent; outline: none;
  flex: 1; min-width: 80px;
  font-size: var(--font-size-sm); color: var(--color-text-primary);
}

/* 字段帮助 */
.field-help-section {
  margin-bottom: var(--spacing-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.field-help-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-tertiary);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
}
.toggle-icon { font-size: var(--font-size-xs); }
.field-help-content {
  max-height: 200px;
  overflow-y: auto;
  padding: var(--spacing-xs) 0;
}
.field-help-empty {
  padding: var(--spacing-sm) var(--spacing-md);
  font-size: var(--font-size-xs);
  color: var(--color-text-quaternary);
  text-align: center;
}
.field-help-item {
  display: flex; align-items: center; gap: var(--spacing-sm);
  padding: var(--spacing-xs) var(--spacing-md);
  cursor: pointer;
  font-size: var(--font-size-sm);
  border-bottom: 1px solid var(--color-border-subtle);
}
.field-help-item:hover { background: var(--color-primary-bg); }
.field-help-item:last-child { border-bottom: none; }
.field-help-name { color: var(--color-text-primary); font-weight: var(--font-weight-medium); min-width: 80px; }
.field-help-column { color: var(--color-text-tertiary); font-family: monospace; font-size: var(--font-size-xs); }
.field-help-type { color: var(--color-text-quaternary); font-size: var(--font-size-xs); background: var(--color-bg-tertiary); padding: 1px 6px; border-radius: var(--radius-sm); }
.field-help-fk { color: var(--color-primary); font-size: var(--font-size-xs); margin-left: auto; }

.condition-input {
  width: 100%; font-family: monospace; resize: vertical;
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-container);
  color: var(--color-text-primary);
}
.condition-hint { font-size: var(--font-size-xs); color: var(--color-text-quaternary); margin-top: 2px; }

.condition-preview {
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-layout);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}
.condition-preview code { font-size: var(--font-size-sm); color: var(--color-primary); font-family: monospace; }
.condition-friendly {
  margin-top: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-md);
  background: var(--color-success-bg, rgba(34,197,94,0.06));
  border: 1px solid var(--color-success-border, rgba(34,197,94,0.15));
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
}
.friendly-label { color: var(--color-success); font-weight: var(--font-weight-medium); }
.friendly-text { color: var(--color-text-primary); }

.preview-section { margin-top: var(--spacing-sm); }
.preview-result { padding: var(--spacing-sm) var(--spacing-md); background: var(--color-bg-layout); border-radius: var(--radius-md); }
.preview-count { font-size: var(--font-size-sm); color: var(--color-text-secondary); font-weight: var(--font-weight-medium); }
.preview-list { display: flex; flex-wrap: wrap; gap: var(--spacing-xs); margin-top: var(--spacing-xs); }
.preview-item { padding: 2px 8px; background: var(--color-primary-bg); border-radius: var(--radius-sm); font-size: var(--font-size-xs); color: var(--color-primary); }
.preview-more { font-size: var(--font-size-xs); color: var(--color-text-quaternary); }

</style>