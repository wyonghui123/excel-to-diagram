<template>
  <el-card class="org-function-panel" shadow="never">
    <template #header>
      <div class="panel-header">
        <span class="panel-title">组织职能视图</span>
        <el-button
          size="small"
          type="primary"
          :disabled="!isAdmin"
          @click="openAddDialog"
        >
          添加职能
        </el-button>
      </div>
    </template>

    <el-table :data="functions" v-loading="loading" empty-text="暂无职能">
      <el-table-column prop="function_type" label="职能类型" min-width="140">
        <template #default="{ row }">
          {{ formatFunctionType(row.function_type) }}
        </template>
      </el-table-column>
      <el-table-column prop="is_primary" label="主职能" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.is_primary" type="success" size="small">是</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180">
        <template #default="{ row }">
          {{ formatDate(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button
            size="small"
            type="danger"
            link
            :disabled="row.is_primary || !isAdmin"
            @click="removeFunction(row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="showAddDialog"
      title="添加组织职能"
      width="480px"
      :close-on-click-modal="false"
    >
      <el-form :model="newFunction" label-width="100px">
        <el-form-item label="职能类型" required>
          <el-select v-model="newFunction.function_type" placeholder="请选择职能类型" style="width: 100%">
            <el-option
              v-for="opt in availableFunctionTypes"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="设为主职能">
          <el-switch v-model="newFunction.is_primary" />
          <span class="form-hint">仅可设一个主职能</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="confirmAdd">
          {{ submitting ? '提交中...' : '确认' }}
        </el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'

const props = defineProps({
  orgId: { type: [String, Number], required: true },
  isAdmin: { type: Boolean, default: false },
})

const functions = ref([])
const loading = ref(false)
const submitting = ref(false)
const showAddDialog = ref(false)
const newFunction = ref({ function_type: 'cost_center', is_primary: false })

const availableFunctionTypes = [
  { value: 'administrative', label: '行政组织' },
  { value: 'legal_entity', label: '法人实体' },
  { value: 'management_unit', label: '管理单元' },
  { value: 'procurement', label: '采购组织' },
  { value: 'accounting', label: '核算组织' },
  { value: 'profit_center', label: '利润中心' },
  { value: 'cost_center', label: '成本中心' },
]

function formatFunctionType(t) {
  const found = availableFunctionTypes.find((o) => o.value === t)
  return found ? found.label : t
}

function formatDate(dt) {
  if (!dt) return '-'
  try {
    return new Date(dt).toLocaleString('zh-CN')
  } catch {
    return dt
  }
}

async function loadFunctions() {
  if (!props.orgId) return
  loading.value = true
  try {
    const resp = await axios.get(`/api/v1/orgs/${props.orgId}/functions`)
    functions.value = resp.data?.data || []
  } catch (e) {
    console.error('[OrgFunctionPanel] load failed:', e)
    ElMessage.error('加载组织职能失败')
  } finally {
    loading.value = false
  }
}

function openAddDialog() {
  newFunction.value = { function_type: 'cost_center', is_primary: false }
  showAddDialog.value = true
}

async function confirmAdd() {
  if (!newFunction.value.function_type) {
    ElMessage.warning('请选择职能类型')
    return
  }
  submitting.value = true
  try {
    await axios.post(`/api/v1/orgs/${props.orgId}/functions`, newFunction.value)
    ElMessage.success('添加成功')
    showAddDialog.value = false
    await loadFunctions()
  } catch (e) {
    console.error('[OrgFunctionPanel] add failed:', e)
    ElMessage.error(e.response?.data?.message || '添加失败')
  } finally {
    submitting.value = false
  }
}

async function removeFunction(row) {
  if (row.is_primary) {
    ElMessage.warning('主职能不可删除')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定要删除职能「${formatFunctionType(row.function_type)}」吗?`,
      '确认删除',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await axios.delete(`/api/v1/orgs/${props.orgId}/functions/${row.function_type}`)
    ElMessage.success('删除成功')
    await loadFunctions()
  } catch (e) {
    console.error('[OrgFunctionPanel] delete failed:', e)
    ElMessage.error(e.response?.data?.message || '删除失败')
  }
}

onMounted(loadFunctions)
</script>

<style scoped>
.org-function-panel {
  margin-top: 12px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.panel-title {
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.form-hint {
  margin-left: 12px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
