<template>
  <div class="role-permission-center">
    <div class="rpc-header">
      <div class="rpc-header__left">
        <h2 class="rpc-title">角色权限配置：{{ role?.name || '加载中...' }}</h2>
        <span v-if="role?.code" class="rpc-subtitle">{{ role.code }}</span>
      </div>
      <div class="rpc-header__right">
        <el-button @click="handleReset" :disabled="saving">
          <el-icon><RefreshLeft /></el-icon>
          重置
        </el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">
          <el-icon><Check /></el-icon>
          保存
        </el-button>
      </div>
    </div>

    <el-container class="rpc-container">
      <el-aside width="20%" class="rpc-aside">
        <ManagementDimensionSelector
          v-model="selectedDimensionId"
          :dimensions="managementDimensions"
          :loading="dimensionsLoading"
          view-mode="list"
          @update:model-value="handleDimensionChange"
        />
      </el-aside>

      <el-main class="rpc-main">
        <div class="rpc-main-content">
          <div class="rpc-top-section">
            <div class="rpc-editor-section">
              <div class="section-header">
                <h3 class="section-title">条件规则编辑器</h3>
              </div>
              <div class="section-content">
                <ConditionRuleEditor
                  ref="ruleEditorRef"
                  v-model="currentRule"
                  :dimension-id="selectedDimensionId"
                  :fields="currentDimensionFields"
                  :dimensions="availableDimensions"
                  :mode="editorMode"
                  @save="handleRuleSave"
                  @cancel="handleRuleCancel"
                  @preview="handleRulePreview"
                />
                <div class="editor-actions">
                  <el-button @click="handleRuleCancel">取消</el-button>
                  <el-button type="primary" @click="handleRuleSubmit">保存规则</el-button>
                </div>
              </div>
            </div>

            <div class="rpc-preview-section">
              <ImpactPreview
                :impact-data="impactData"
                :loading="impactLoading"
                @export="handleExportImpact"
                @filter-change="handleImpactFilterChange"
              />
            </div>
          </div>

          <div class="rpc-bottom-section">
            <div class="section-header">
              <h3 class="section-title">已配置规则列表（共 {{ permissionRules.length }} 条）</h3>
              <div class="section-actions">
                <el-input
                  v-model="ruleSearchKeyword"
                  placeholder="搜索规则..."
                  clearable
                  style="width: 200px;"
                >
                  <template #prefix>
                    <el-icon><Search /></el-icon>
                  </template>
                </el-input>
              </div>
            </div>
            <el-table
              :data="filteredPermissionRules"
              style="width: 100%"
              border
              stripe
              max-height="300"
              @sort-change="handleRuleSortChange"
            >
              <el-table-column
                prop="dimension_name"
                label="维度"
                width="120"
                sortable="custom"
              >
                <template #default="{ row }">
                  <span>{{ getDimensionName(row.resource_type) }}</span>
                </template>
              </el-table-column>
              <el-table-column
                prop="condition"
                label="条件"
                min-width="200"
                show-overflow-tooltip
              >
                <template #default="{ row }">
                  <code class="condition-code">{{ row.condition }}</code>
                </template>
              </el-table-column>
              <el-table-column
                prop="permission_level"
                label="权限级别"
                width="100"
                sortable="custom"
              >
                <template #default="{ row }">
                  <el-tag :type="getPermissionLevelType(row.permission_level)" size="small">
                    {{ getPermissionLevelLabel(row.permission_level) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                prop="inherit_to_children"
                label="继承"
                width="80"
                align="center"
              >
                <template #default="{ row }">
                  <el-icon v-if="row.inherit_to_children" color="#52c41a"><Check /></el-icon>
                  <el-icon v-else color="#d9d9d9"><Close /></el-icon>
                </template>
              </el-table-column>
              <el-table-column
                prop="is_denied"
                label="禁止"
                width="80"
                align="center"
              >
                <template #default="{ row }">
                  <el-tag v-if="row.is_denied" type="danger" size="small">禁止</el-tag>
                  <span v-else>-</span>
                </template>
              </el-table-column>
              <el-table-column
                prop="is_enabled"
                label="状态"
                width="80"
                align="center"
              >
                <template #default="{ row }">
                  <el-switch
                    v-model="row.is_enabled"
                    @change="handleRuleStatusChange(row)"
                  />
                </template>
              </el-table-column>
              <el-table-column
                label="操作"
                width="150"
                fixed="right"
              >
                <template #default="{ row }">
                  <el-button type="primary" link size="small" @click="handleEditRule(row)">
                    编辑
                  </el-button>
                  <el-button type="danger" link size="small" @click="handleDeleteRule(row)">
                    删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </el-main>
    </el-container>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from '@/composables/useMessage'
import { RefreshLeft, Check, Search, Close } from '@element-plus/icons-vue'
import ManagementDimensionSelector from '@/components/common/ManagementDimensionSelector/ManagementDimensionSelector.vue'
import ConditionRuleEditor from '@/components/common/ConditionRuleEditor/ConditionRuleEditor.vue'
import ImpactPreview from '@/components/common/ImpactPreview/ImpactPreview.vue'
import * as permService from '@/services/permissionService'

const route = useRoute()
const router = useRouter()
const { success, error, warning } = useMessage()

const roleId = computed(() => {
  const id = route.params.roleId || route.params.id
  return id ? parseInt(id) : null
})

const role = ref(null)
const saving = ref(false)

const managementDimensions = ref([])
const dimensionsLoading = ref(false)
const selectedDimensionId = ref('')
const currentDimensionFields = ref([])

const permissionRules = ref([])
const ruleSearchKeyword = ref('')
const ruleSortProp = ref('')
const ruleSortOrder = ref('')

const currentRule = ref({})
const editorMode = ref('create')
const ruleEditorRef = ref(null)

const impactData = ref({})
const impactLoading = ref(false)

const availableDimensions = computed(() => {
  return managementDimensions.value.map(dim => ({
    code: dim.code || dim.id,
    name: dim.name,
    field: dim.field || dim.code,
    relation_object: dim.relation_object,
    cascade_parent: dim.cascade_parent,
    resource_types: dim.resource_types
  }))
})

const filteredPermissionRules = computed(() => {
  let result = [...permissionRules.value]
  
  if (ruleSearchKeyword.value) {
    const keyword = ruleSearchKeyword.value.toLowerCase()
    result = result.filter(rule => 
      (rule.condition && rule.condition.toLowerCase().includes(keyword)) ||
      (rule.resource_type && rule.resource_type.toLowerCase().includes(keyword))
    )
  }
  
  if (ruleSortProp.value && ruleSortOrder.value) {
    result = [...result].sort((a, b) => {
      const aVal = a[ruleSortProp.value] || ''
      const bVal = b[ruleSortProp.value] || ''
      const compareResult = String(aVal).localeCompare(String(bVal), 'zh-CN')
      return ruleSortOrder.value === 'ascending' ? compareResult : -compareResult
    })
  }
  
  return result
})

async function loadRole() {
  if (!roleId.value) {
    console.warn('No role ID provided')
    return
  }

  try {
    const r = await permService.loadRole(roleId.value)
    role.value = r.data || r
  } catch (e) {
    console.error('Failed to load role:', e)
    error('加载角色信息失败')
  }
}

async function loadManagementDimensions() {
  dimensionsLoading.value = true

  try {
    const r = await permService.loadDimensions()
    const dims = r.data?.dimensions || r.data || []

    managementDimensions.value = dims.map(dim => ({
      ...dim,
      ruleCount: permissionRules.value.filter(rule => rule.resource_type === dim.code || rule.resource_type === dim.id).length
    }))
  } catch (e) {
    console.error('Failed to load management dimensions:', e)
    error('加载管理维度失败')
  } finally {
    dimensionsLoading.value = false
  }
}

async function loadDimensionFields(dimensionId) {
  if (!dimensionId) {
    currentDimensionFields.value = []
    return
  }

  try {
    const r = await permService.loadDimensionFields(dimensionId)
    currentDimensionFields.value = r.data || []
  } catch (e) {
    console.error('Failed to load dimension fields:', e)
    currentDimensionFields.value = []
  }
}

async function loadPermissionRules() {
  if (!roleId.value) return

  try {
    const r = await permService.loadPermissionRules(roleId.value)
    permissionRules.value = r.data?.rules || r.data || []
  } catch (e) {
    console.error('Failed to load permission rules:', e)
    error('加载权限规则失败')
  }
}

async function calculateImpact(rule) {
  if (!roleId.value || !rule.condition) return

  impactLoading.value = true

  try {
    const r = await permService.calculateImpact(roleId.value, {
      resource_type: rule.resource_type,
      condition: rule.condition,
      permission_level: rule.permission_level,
      inherit_to_children: rule.inherit_to_children,
      propagate_to_parents: rule.propagate_to_parents,
    })
    impactData.value = r.data || r
  } catch (e) {
    console.error('Failed to calculate impact:', e)
    error('计算影响范围失败')
  } finally {
    impactLoading.value = false
  }
}

function handleDimensionChange(dimensionId) {
  selectedDimensionId.value = dimensionId
  loadDimensionFields(dimensionId)
  
  editorMode.value = 'create'
  currentRule.value = {}
  
  if (ruleEditorRef.value) {
    ruleEditorRef.value.reset()
  }
}

function handleRuleSave(rule) {
  currentRule.value = { ...rule }
}

function handleRuleCancel() {
  editorMode.value = 'create'
  currentRule.value = {}
  
  if (ruleEditorRef.value) {
    ruleEditorRef.value.reset()
  }
}

function handleRulePreview(previewData) {
  calculateImpact(previewData)
}

async function handleRuleSubmit() {
  if (!ruleEditorRef.value) return

  const isValid = ruleEditorRef.value.validate()
  if (!isValid) {
    warning('请完善规则信息')
    return
  }

  const ruleData = ruleEditorRef.value.getFormData()

  try {
    const mode = editorMode.value === 'edit' ? 'update' : 'create'
    const rule = editorMode.value === 'edit' ? { ...ruleData, id: currentRule.value.id } : ruleData
    await permService.savePermissionRules(roleId.value, rule, mode)

    success(editorMode.value === 'edit' ? '规则已更新' : '规则已创建')

    await loadPermissionRules()
    await calculateImpact(ruleData)

    editorMode.value = 'create'
    currentRule.value = {}
    ruleEditorRef.value.reset()
  } catch (e) {
    console.error('Failed to save rule:', e)
    error('保存规则失败')
  }
}

function handleEditRule(row) {
  editorMode.value = 'edit'
  currentRule.value = { ...row }
  
  const dimension = managementDimensions.value.find(d => 
    d.code === row.resource_type || d.id === row.resource_type
  )
  
  if (dimension) {
    selectedDimensionId.value = dimension.id || dimension.code
    loadDimensionFields(dimension.id || dimension.code)
  }
}

async function handleDeleteRule(row) {
  const confirmed = await messageConfirm({ content: `确定要删除该规则吗？\n\n条件: ${row.condition}` })
  if (!confirmed) return

  try {
    await permService.deletePermissionRule(roleId.value, row.id)

    success('规则已删除')
    await loadPermissionRules()

    if (selectedDimensionId.value) {
      await calculateImpact(currentRule.value)
    }
  } catch (e) {
    console.error('Failed to delete rule:', e)
    error('删除规则失败')
  }
}

async function handleRuleStatusChange(row) {
  try {
    await permService.patchPermissionRule(roleId.value, row.id, { is_enabled: row.is_enabled })
    success(row.is_enabled ? '规则已启用' : '规则已禁用')
  } catch (e) {
    console.error('Failed to update rule status:', e)
    error('更新规则状态失败')
    row.is_enabled = !row.is_enabled
  }
}

function handleRuleSortChange({ prop, order }) {
  ruleSortProp.value = prop || ''
  ruleSortOrder.value = order || ''
}

function handleExportImpact(data) {
  success(`已导出 ${data.count} 条影响范围数据`)
}

function handleImpactFilterChange(filter) {
  console.log('Impact filter changed:', filter)
}

async function handleSave() {
  if (!roleId.value) {
    error('无法保存：缺少角色ID')
    return
  }

  saving.value = true

  try {
    await permService.savePermissionRules(roleId.value, { rules: permissionRules.value }, 'batch')
    success('权限配置已保存')
  } catch (e) {
    console.error('Save failed:', e)
    error('保存失败: ' + e.message)
  } finally {
    saving.value = false
  }
}

function handleReset() {
  selectedDimensionId.value = ''
  currentDimensionFields.value = []
  currentRule.value = {}
  editorMode.value = 'create'
  impactData.value = {}
  
  if (ruleEditorRef.value) {
    ruleEditorRef.value.reset()
  }
  
  loadRole()
  loadManagementDimensions()
  loadPermissionRules()
}

function getDimensionName(resourceType) {
  return permService.getDimensionName(managementDimensions.value, resourceType)
}

function getPermissionLevelType(level) {
  return permService.getPermissionLevelType(level)
}

function getPermissionLevelLabel(level) {
  return permService.getPermissionLevelLabel(level)
}

watch(permissionRules, () => {
  managementDimensions.value = managementDimensions.value.map(dim => ({
    ...dim,
    ruleCount: permissionRules.value.filter(r => 
      r.resource_type === dim.code || r.resource_type === dim.id
    ).length
  }))
}, { deep: true })

onMounted(() => {
  loadRole()
  loadManagementDimensions()
  loadPermissionRules()
})
</script>

<style scoped>
.role-permission-center {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-layout, #f5f5f5);
}

.rpc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  background: var(--color-bg-container, #fff);
  border-bottom: 1px solid var(--color-border-secondary, #f0f0f0);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.rpc-header__left {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.rpc-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary, rgba(0, 0, 0, 0.85));
}

.rpc-subtitle {
  font-size: 14px;
  color: var(--color-text-secondary, rgba(0, 0, 0, 0.45));
  font-family: monospace;
}

.rpc-header__right {
  display: flex;
  gap: 12px;
}

.rpc-container {
  flex: 1;
  overflow: hidden;
}

.rpc-aside {
  background: var(--color-bg-container, #fff);
  border-right: 1px solid var(--color-border-secondary, #f0f0f0);
  overflow-y: auto;
}

.rpc-main {
  padding: 0;
  overflow: hidden;
}

.rpc-main-content {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
}

.rpc-top-section {
  display: flex;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.rpc-editor-section,
.rpc-preview-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-container, #fff);
  border-radius: 8px;
  border: 1px solid var(--color-border-secondary, #f0f0f0);
  overflow: hidden;
}

.section-header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border-secondary, #f0f0f0);
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--color-bg-secondary, #fafafa);
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary, rgba(0, 0, 0, 0.85));
}

.section-content {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.editor-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border-secondary, #f0f0f0);
}

.rpc-bottom-section {
  background: var(--color-bg-container, #fff);
  border-radius: 8px;
  border: 1px solid var(--color-border-secondary, #f0f0f0);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  max-height: 400px;
}

.rpc-bottom-section .section-header {
  flex-shrink: 0;
}

.section-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.rpc-bottom-section .el-table {
  flex: 1;
  overflow: auto;
}

.condition-code {
  font-family: monospace;
  font-size: 12px;
  color: var(--color-primary, #1890ff);
  background: var(--color-primary-bg, #e6f7ff);
  padding: 2px 6px;
  border-radius: 4px;
}

@media (max-width: 1200px) {
  .rpc-top-section {
    flex-direction: column;
  }
  
  .rpc-editor-section,
  .rpc-preview-section {
    max-height: 50%;
  }
}

@media (max-width: 768px) {
  .rpc-header {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }
  
  .rpc-header__right {
    justify-content: flex-end;
  }
  
  .rpc-aside {
    width: 100% !important;
    max-height: 200px;
  }
  
  .rpc-container {
    flex-direction: column;
  }
}
</style>
