<template>
  <PageShell title="打印模板与绑定" :show-back-button="false">
    <template #title-bar-actions>
      <AppButton variant="secondary" size="sm" :loading="loading" @click="reloadAll">刷新</AppButton>
    </template>

    <div class="print-admin">
      <AppAlert v-if="loadError" type="error">{{ loadError }}</AppAlert>
      <AppAlert type="info">
        可打印接入点由 BO 元数据派生（header 类型 ∩ 具备编号/单据影响），不手工注册；
        模板变量白名单在发布时冻结（spec §4 / D-PR-02）。
      </AppAlert>

      <el-tabs v-model="activeTab" class="print-admin__tabs">
        <!-- ---------------------------------------------------------- 模板 -->
        <el-tab-pane label="模板" name="templates">
          <div class="print-admin__filters">
            <el-select v-model="tplFilters.bo_code" placeholder="全部业务对象" clearable
                       style="width:180px" @change="handleTplBoChange">
              <el-option v-for="bo in boOptions" :key="bo.bo_code" :label="bo.bo_name" :value="bo.bo_code" />
            </el-select>
            <el-select v-model="tplFilters.type_code" placeholder="全部单据类型" clearable
                       style="width:180px" @change="loadTemplates">
              <el-option v-for="type in tplTypeOptions" :key="type.type_code"
                         :label="`${type.type_name}（${type.type_code}）`" :value="type.type_code" />
            </el-select>
            <el-select v-model="tplFilters.status" placeholder="全部状态" clearable
                       style="width:140px" @change="loadTemplates">
              <el-option label="草稿" value="draft" />
              <el-option label="生效" value="active" />
              <el-option label="已归档" value="archived" />
              <el-option label="已过期" value="stale" />
            </el-select>
            <AppButton variant="primary" size="sm" :disabled="!canCreate" @click="openCreate">
              新建模板
            </AppButton>
            <AppButton variant="secondary" size="sm" :disabled="!canCreate" @click="openForkDefault">
              从默认版式新建
            </AppButton>
            <span class="print-admin__hint">默认版式由元数据渲染期合成，不落模板表（D-PR-16）</span>
          </div>

          <MetaTable
            :columns="templateColumns"
            :data="templates"
            :loading="tplLoading"
            :search-placeholder="null"
            :show-pagination="false"
            row-key="id"
            empty-type="folder"
            empty-title="暂无模板"
            empty-description="未配置模板时单据仍可打印（合成默认版式）"
          >
            <template #cell-template="{ row }">
              <div class="print-admin__cell">
                <span class="print-admin__strong">{{ row.name }}</span>
                <span class="print-admin__muted">{{ row.code }} · {{ row.bo_code }}<template v-if="row.type_code"> / {{ row.type_code }}</template></span>
              </div>
            </template>
            <template #cell-version="{ row }">v{{ row.version }}</template>
            <template #cell-status="{ row }">
              <span class="print-admin__badge" :class="`print-admin__badge--${statusTone(row.status)}`">
                {{ statusLabel(row.status) }}
              </span>
            </template>
            <template #cell-paper="{ row }">{{ row.paper_size }} · {{ row.orientation === 'landscape' ? '横向' : '纵向' }}</template>
            <template #cell-scope="{ row }">{{ scopeLabel(row) }}</template>
            <template #cell-published="{ row }">{{ row.published_at || '—' }}</template>
            <template #cell-actions="{ row }">
              <div class="print-admin__actions">
                <AppButton variant="text" size="xs" :disabled="!canUpdate || row.status !== 'draft'" @click="openEdit(row)">编辑</AppButton>
                <AppButton variant="text" size="xs" :disabled="!canUpdate" @click="handleValidate(row)">校验</AppButton>
                <AppButton variant="text" size="xs" :disabled="!canUpdate || row.status !== 'draft'" @click="handlePublish(row)">发布</AppButton>
              </div>
            </template>
          </MetaTable>
        </el-tab-pane>

        <!-- ---------------------------------------------------------- 绑定 -->
        <el-tab-pane label="绑定" name="bindings">
          <div class="print-admin__filters">
            <el-select v-model="bindFilters.bo_code" placeholder="选择业务对象" style="width:180px"
                       @change="handleBindBoChange">
              <el-option v-for="bo in boOptions" :key="bo.bo_code" :label="bo.bo_name" :value="bo.bo_code" />
            </el-select>
            <el-select v-model="bindFilters.type_code" placeholder="BO 级默认（全部类型）" clearable
                       style="width:180px" @change="loadBindings">
              <el-option v-for="type in bindTypeOptions" :key="type.type_code"
                         :label="`${type.type_name}（${type.type_code}）`" :value="type.type_code" />
            </el-select>
            <AppButton variant="primary" size="sm" :disabled="!canCreate || !bindFilters.bo_code" @click="openCreateBinding">
              新建绑定
            </AppButton>
            <span class="print-admin__hint">默认 + 条件 + 优先级，不引入规则引擎（D-PR-11）</span>
          </div>

          <MetaTable
            :columns="bindingColumns"
            :data="bindings"
            :loading="bindLoading"
            :search-placeholder="null"
            :show-pagination="false"
            row-key="id"
            empty-type="folder"
            empty-title="暂无绑定"
            empty-description="未绑定模板时走合成默认版式"
          >
            <template #cell-type="{ row }">{{ row.type_code || 'BO 级默认' }}</template>
            <template #cell-template="{ row }">#{{ row.template_id }}</template>
            <template #cell-priority="{ row }">{{ row.priority }}</template>
            <template #cell-default="{ row }">{{ row.is_default ? '是' : '否' }}</template>
            <template #cell-active="{ row }">
              <span class="print-admin__badge" :class="`print-admin__badge--${row.is_active ? 'success' : 'danger'}`">
                {{ row.is_active ? '启用' : '停用' }}
              </span>
            </template>
            <template #cell-condition="{ row }">{{ conditionText(row.condition) }}</template>
            <template #cell-actions="{ row }">
              <div class="print-admin__actions">
                <AppButton variant="text" size="xs" :disabled="!canUpdate" @click="openEditBinding(row)">编辑</AppButton>
                <AppButton variant="text" size="xs" :disabled="!canDelete || !row.is_active" @click="handleDeleteBinding(row)">停用</AppButton>
              </div>
            </template>
          </MetaTable>
        </el-tab-pane>

        <!-- ---------------------------------------------------------- 试算 -->
        <el-tab-pane label="命中试算" name="resolve">
          <div class="print-admin__filters">
            <el-select v-model="resolveForm.bo_code" placeholder="业务对象" style="width:180px"
                       @change="resolveForm.type_code = ''">
              <el-option v-for="bo in boOptions" :key="bo.bo_code" :label="bo.bo_name" :value="bo.bo_code" />
            </el-select>
            <el-select v-model="resolveForm.type_code" placeholder="全部类型" clearable style="width:180px">
              <el-option v-for="type in resolveTypeOptions" :key="type.type_code"
                         :label="`${type.type_name}（${type.type_code}）`" :value="type.type_code" />
            </el-select>
            <el-input v-model="resolveForm.doc_id" placeholder="单据 ID" style="width:180px" />
            <AppButton variant="primary" size="sm" :loading="resolveLoading" :disabled="!resolveForm.bo_code" @click="handleResolve">
              试算
            </AppButton>
          </div>

          <AppAlert v-if="resolveResult" :type="resolveResult.uses_default_layout ? 'warning' : 'success'">
            命中 {{ resolveResult.uses_default_layout ? '合成默认版式' : `模板 ${resolveResult.template?.name} v${resolveResult.template?.version}` }}
            <template v-if="resolveResult.reason"> · 原因：{{ resolveResult.reason }}</template>
          </AppAlert>
          <pre v-if="resolveResult" class="print-admin__json">{{ resolveSummaryText }}</pre>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 模板编辑 -->
    <Drawer v-model="editorVisible" :title="editingId ? '编辑模板（仅草稿）' : '新建模板'" width="960px">
      <div class="print-admin__form">
        <div class="print-admin__grid">
          <el-select v-model="editorForm.bo_code" placeholder="业务对象" :disabled="Boolean(editingId)"
                     @change="editorForm.type_code = ''">
            <el-option v-for="bo in boOptions" :key="bo.bo_code" :label="bo.bo_name" :value="bo.bo_code" />
          </el-select>
          <el-select v-model="editorForm.type_code" placeholder="全部类型" clearable :disabled="Boolean(editingId)">
            <el-option v-for="type in editorTypeOptions" :key="type.type_code"
                       :label="`${type.type_name}（${type.type_code}）`" :value="type.type_code" />
          </el-select>
          <el-input v-model="editorForm.code" placeholder="模板编码（跨版本稳定）" :disabled="Boolean(editingId)" />
          <el-input v-model="editorForm.name" placeholder="模板名称" />
          <el-select v-model="editorForm.paper_size" placeholder="纸张">
            <el-option v-for="paper in paperOptions" :key="paper" :label="paper" :value="paper" />
          </el-select>
          <el-select v-model="editorForm.orientation" placeholder="方向">
            <el-option label="纵向" value="portrait" />
            <el-option label="横向" value="landscape" />
          </el-select>
        </div>

        <div class="print-admin__margins">
          <el-input-number v-model="editorForm.margin_top" :min="0" :max="100" size="small" />
          <el-input-number v-model="editorForm.margin_right" :min="0" :max="100" size="small" />
          <el-input-number v-model="editorForm.margin_bottom" :min="0" :max="100" size="small" />
          <el-input-number v-model="editorForm.margin_left" :min="0" :max="100" size="small" />
          <span class="print-admin__hint">页边距（mm）：上 / 右 / 下 / 左</span>
        </div>

        <div class="print-admin__field">
          <label v-pre>模板 HTML（变量 {{path}}，控制流仅 #if / #each）</label>
          <el-input v-model="editorForm.html" type="textarea" :rows="16" class="print-admin__code" spellcheck="false" />
        </div>
        <div class="print-admin__field">
          <label>模板 CSS</label>
          <el-input v-model="editorForm.css" type="textarea" :rows="8" class="print-admin__code" spellcheck="false" />
        </div>

        <AppAlert v-if="editorErrors.length" type="error">
          <div v-for="(item, index) in editorErrors" :key="index">
            {{ item.message || item.code }}{{ item.field ? `（${item.field}）` : '' }}
          </div>
        </AppAlert>
        <AppAlert v-if="editorWarnings.length" type="warning">
          <div v-for="(item, index) in editorWarnings" :key="index">
            {{ item.message || item.code }}
          </div>
        </AppAlert>
      </div>
      <template #footer>
        <div class="print-admin__footer">
          <AppButton variant="secondary" size="sm" @click="editorVisible = false">取消</AppButton>
          <AppButton variant="secondary" size="sm" :loading="editorValidating" :disabled="!canUpdate" @click="validateEditorContent">
            校验内容
          </AppButton>
          <AppButton variant="primary" size="sm" :loading="editorSaving" :disabled="!canCreate && !canUpdate" @click="saveTemplate">
            保存草稿
          </AppButton>
        </div>
      </template>
    </Drawer>

    <!-- 绑定编辑 -->
    <Drawer v-model="bindingVisible" :title="bindingEditingId ? '编辑绑定' : '新建绑定'" width="620px">
      <div class="print-admin__form">
        <div class="print-admin__field">
          <label>业务对象</label>
          <el-select v-model="bindingForm.bo_code" disabled>
            <el-option v-for="bo in boOptions" :key="bo.bo_code" :label="bo.bo_name" :value="bo.bo_code" />
          </el-select>
        </div>
        <div class="print-admin__field">
          <label>单据类型</label>
          <el-select v-model="bindingForm.type_code" placeholder="BO 级默认（全部类型）" clearable :disabled="Boolean(bindingEditingId)">
            <el-option v-for="type in bindTypeOptions" :key="type.type_code"
                       :label="`${type.type_name}（${type.type_code}）`" :value="type.type_code" />
          </el-select>
        </div>
        <div class="print-admin__field">
          <label>模板</label>
          <el-select v-model="bindingForm.template_id" placeholder="选择模板" filterable>
            <el-option v-for="tpl in bindingTemplateOptions" :key="tpl.id"
                       :label="`${tpl.name} v${tpl.version}（${tpl.status}）`" :value="tpl.id" />
          </el-select>
        </div>
        <div class="print-admin__grid print-admin__grid--two">
          <el-input-number v-model="bindingForm.priority" :min="1" :max="9999" />
          <el-switch v-model="bindingForm.is_default" active-text="默认绑定" />
        </div>
        <div class="print-admin__field">
          <label>条件 JSON（字段须在 BO 白名单内，如 {"currency":"CNY"}）</label>
          <el-input v-model="bindingForm.condition_text" type="textarea" :rows="4" class="print-admin__code" spellcheck="false" />
        </div>
        <div class="print-admin__grid print-admin__grid--two">
          <el-select v-model="bindingForm.scope_type">
            <el-option label="系统" value="system" />
            <el-option label="租户" value="tenant" />
            <el-option label="组织" value="org" />
          </el-select>
          <el-input v-model="bindingForm.scope_id" placeholder="作用域 ID（可选）" />
        </div>
      </div>
      <template #footer>
        <div class="print-admin__footer">
          <AppButton variant="secondary" size="sm" @click="bindingVisible = false">取消</AppButton>
          <AppButton variant="primary" size="sm" :loading="bindingSaving" @click="saveBinding">保存</AppButton>
        </div>
      </template>
    </Drawer>

    <!-- 从默认版式新建 -->
    <Drawer v-model="forkVisible" title="从默认版式新建" width="520px">
      <div class="print-admin__form">
        <AppAlert type="info">将以当前 BO 元数据合成默认版式为内容，创建一份 draft 模板。</AppAlert>
        <div class="print-admin__field">
          <label>业务对象</label>
          <el-select v-model="forkForm.bo_code" placeholder="选择业务对象" @change="forkForm.type_code = ''">
            <el-option v-for="bo in boOptions" :key="bo.bo_code" :label="bo.bo_name" :value="bo.bo_code" />
          </el-select>
        </div>
        <div class="print-admin__field">
          <label>单据类型</label>
          <el-select v-model="forkForm.type_code" placeholder="BO 级默认（全部类型）" clearable>
            <el-option v-for="type in forkTypeOptions" :key="type.type_code"
                       :label="`${type.type_name}（${type.type_code}）`" :value="type.type_code" />
          </el-select>
        </div>
      </div>
      <template #footer>
        <div class="print-admin__footer">
          <AppButton variant="secondary" size="sm" @click="forkVisible = false">取消</AppButton>
          <AppButton variant="primary" size="sm" :loading="forking" :disabled="!forkForm.bo_code" @click="handleForkDefault">
            创建草稿
          </AppButton>
        </div>
      </template>
    </Drawer>
  </PageShell>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { AppAlert, AppButton, Drawer, MetaTable, PageShell } from '@/components/common'
import { useMessage } from '@/composables/useMessage'
import { useAuthStore } from '@/stores/authStore'
import {
  createBinding,
  createTemplate,
  deleteBinding,
  fetchBindings,
  fetchPrintable,
  fetchTemplate,
  fetchTemplates,
  forkDefaultTemplate,
  publishTemplate,
  resolveTemplate,
  updateBinding,
  updateTemplate,
  validateTemplate
} from '@/services/printService'

const message = useMessage()
const authStore = useAuthStore()

const activeTab = ref('templates')
const loading = ref(false)
const loadError = ref('')

const canCreate = computed(() => authStore.hasPermission('print_template:create'))
const canUpdate = computed(() => authStore.hasPermission('print_template:update'))
const canDelete = computed(() => authStore.hasPermission('print_template:delete'))

const paperOptions = ['A4', 'A5', 'A3', 'Letter', 'Legal']
const scopeLabels = { system: '系统', tenant: '租户', org: '组织' }
const statusLabels = { draft: '草稿', active: '生效', archived: '已归档', stale: '已过期' }
const statusTones = { draft: 'warning', active: 'success', archived: 'muted', stale: 'danger' }

function statusLabel(value) {
  return statusLabels[value] || value || '—'
}
function statusTone(value) {
  return statusTones[value] || 'muted'
}
function scopeLabel(row) {
  const base = scopeLabels[row.scope_type] || row.scope_type || '—'
  return row.scope_id ? `${base} · ${row.scope_id}` : base
}
function conditionText(condition) {
  if (!condition || !Object.keys(condition).length) return '无条件'
  return JSON.stringify(condition)
}

// ------------------------------------------------------------------ 接入点

const printable = ref([])
const boOptions = computed(() => {
  const seen = new Map()
  for (const item of printable.value) {
    if (!seen.has(item.bo_code)) seen.set(item.bo_code, { bo_code: item.bo_code, bo_name: item.bo_name || item.bo_code })
  }
  return [...seen.values()]
})
function typeOptionsOf(boCode) {
  return printable.value.filter((item) => item.bo_code === boCode)
}

// ------------------------------------------------------------------ 模板

const tplFilters = reactive({ bo_code: '', type_code: '', status: '' })
const templates = ref([])
const tplLoading = ref(false)
const tplTypeOptions = computed(() => typeOptionsOf(tplFilters.bo_code))

const templateColumns = [
  { key: 'template', label: '模板', slot: true, width: '240px' },
  { key: 'version', label: '版本', slot: true, width: '70px' },
  { key: 'status', label: '状态', slot: true, width: '90px' },
  { key: 'paper', label: '纸张', slot: true, width: '150px' },
  { key: 'scope', label: '作用域', slot: true, width: '130px' },
  { key: 'published', label: '发布时间', slot: true, width: '170px' },
  { key: 'actions', label: '操作', slot: true, width: '190px' }
]

async function loadTemplates() {
  tplLoading.value = true
  try {
    const response = await fetchTemplates({
      bo_code: tplFilters.bo_code || undefined,
      type_code: tplFilters.type_code || undefined,
      status: tplFilters.status || undefined,
      page_size: 200
    })
    templates.value = response.success ? (response.data || []) : []
  } catch (error) {
    message.error('模板列表加载失败', error)
  } finally {
    tplLoading.value = false
  }
}

function handleTplBoChange() {
  tplFilters.type_code = ''
  loadTemplates()
}

const editorVisible = ref(false)
const editingId = ref(null)
const editorSaving = ref(false)
const editorValidating = ref(false)
const editorErrors = ref([])
const editorWarnings = ref([])
const editorForm = reactive({
  bo_code: '', type_code: '', code: '', name: '', version: 1,
  status: 'draft', html: '', css: '', paper_size: 'A4', orientation: 'portrait',
  margin_top: 10, margin_right: 10, margin_bottom: 10, margin_left: 10,
  scope_type: 'system', scope_id: ''
})
const editorTypeOptions = computed(() => typeOptionsOf(editorForm.bo_code))

function resetEditor() {
  Object.assign(editorForm, {
    bo_code: tplFilters.bo_code || '', type_code: tplFilters.type_code || '',
    code: '', name: '', version: 1, status: 'draft', html: '', css: '',
    paper_size: 'A4', orientation: 'portrait',
    margin_top: 10, margin_right: 10, margin_bottom: 10, margin_left: 10,
    scope_type: 'system', scope_id: ''
  })
  editorErrors.value = []
  editorWarnings.value = []
}

function openCreate() {
  editingId.value = null
  resetEditor()
  editorVisible.value = true
}

async function openEdit(row) {
  editingId.value = row.id
  resetEditor()
  try {
    const response = await fetchTemplate(row.id)
    if (!response.success) {
      message.error(response.message || '模板加载失败')
      return
    }
    const detail = response.data || {}
    Object.assign(editorForm, {
      bo_code: row.bo_code,
      type_code: row.type_code || '',
      code: row.code,
      name: row.name,
      version: row.version,
      status: row.status,
      html: detail.html || '',
      css: detail.css || '',
      paper_size: row.paper_size || 'A4',
      orientation: row.orientation || 'portrait',
      margin_top: row.margin_top ?? 10,
      margin_right: row.margin_right ?? 10,
      margin_bottom: row.margin_bottom ?? 10,
      margin_left: row.margin_left ?? 10,
      scope_type: row.scope_type || 'system',
      scope_id: row.scope_id || ''
    })
    if (!detail.html && !detail.css) {
      message.warning('未读取到模板正文（需要 print_template:read）')
    }
    editorVisible.value = true
  } catch (error) {
    message.error('模板加载失败', error)
  }
}

function editorPayload() {
  return {
    bo_code: editorForm.bo_code,
    type_code: editorForm.type_code || '',
    code: editorForm.code,
    name: editorForm.name,
    html: editorForm.html,
    css: editorForm.css,
    paper_size: editorForm.paper_size,
    orientation: editorForm.orientation,
    margin_top: editorForm.margin_top,
    margin_right: editorForm.margin_right,
    margin_bottom: editorForm.margin_bottom,
    margin_left: editorForm.margin_left,
    scope_type: editorForm.scope_type,
    scope_id: editorForm.scope_id || null
  }
}

function collectFeedback(response) {
  const data = response.data || {}
  editorErrors.value = data.errors || []
  editorWarnings.value = data.warnings || []
}

async function saveTemplate() {
  if (!editorForm.bo_code || !editorForm.code || !editorForm.name || !editorForm.html) {
    message.error('业务对象 / 编码 / 名称 / HTML 为必填')
    return
  }
  editorSaving.value = true
  try {
    const response = editingId.value
      ? await updateTemplate(editingId.value, editorPayload())
      : await createTemplate(editorPayload())
    if (!response.success) {
      message.error(response.message || '保存失败')
      collectFeedback(response)
      return
    }
    collectFeedback(response)
    message.success(editingId.value ? '模板已保存' : '模板草稿已创建')
    await loadTemplates()
    if (!editorErrors.value.length) editorVisible.value = false
  } catch (error) {
    message.error('保存失败', error)
  } finally {
    editorSaving.value = false
  }
}

async function validateEditorContent() {
  if (!editingId.value) {
    message.warning('请先保存草稿后再校验')
    return
  }
  editorValidating.value = true
  try {
    const response = await validateTemplate(editingId.value)
    if (!response.success) {
      message.error(response.message || '校验失败')
      return
    }
    editorErrors.value = response.data?.errors || []
    editorWarnings.value = response.data?.warnings || []
    if (response.data?.valid) message.success('校验通过')
  } catch (error) {
    message.error('校验失败', error)
  } finally {
    editorValidating.value = false
  }
}

async function handleValidate(row) {
  try {
    const response = await validateTemplate(row.id)
    if (!response.success) {
      message.error(response.message || '校验失败')
      return
    }
    const errors = response.data?.errors || []
    if (errors.length) {
      message.error(`校验未通过：${errors.length} 项问题`)
    } else {
      message.success('校验通过')
    }
  } catch (error) {
    message.error('校验失败', error)
  }
}

async function handlePublish(row) {
  const confirmed = await message.confirm({
    title: '发布模板',
    content: `发布后 v${row.version} 冻结为生效版本且不可编辑，确认发布「${row.name}」？`,
    type: 'warning'
  })
  if (!confirmed) return
  try {
    const response = await publishTemplate(row.id)
    if (!response.success) {
      message.error(response.message || '发布失败')
      return
    }
    message.success('模板已发布')
    await loadTemplates()
  } catch (error) {
    message.error('发布失败', error)
  }
}

// ------------------------------------------------------------------ 从默认版式新建

const forkVisible = ref(false)
const forking = ref(false)
const forkForm = reactive({ bo_code: '', type_code: '' })
const forkTypeOptions = computed(() => typeOptionsOf(forkForm.bo_code))

function openForkDefault() {
  forkForm.bo_code = tplFilters.bo_code || ''
  forkForm.type_code = tplFilters.type_code || ''
  forkVisible.value = true
}

async function handleForkDefault() {
  forking.value = true
  try {
    const response = await forkDefaultTemplate(0, {
      bo_code: forkForm.bo_code,
      type_code: forkForm.type_code || ''
    })
    if (!response.success) {
      message.error(response.message || '创建失败')
      return
    }
    message.success('已从默认版式创建草稿')
    forkVisible.value = false
    tplFilters.bo_code = forkForm.bo_code
    tplFilters.type_code = forkForm.type_code || ''
    await loadTemplates()
  } catch (error) {
    message.error('创建失败', error)
  } finally {
    forking.value = false
  }
}

// ------------------------------------------------------------------ 绑定

const bindFilters = reactive({ bo_code: '', type_code: '' })
const bindings = ref([])
const bindLoading = ref(false)
const bindingTemplateOptions = ref([])
const bindTypeOptions = computed(() => typeOptionsOf(bindFilters.bo_code))

const bindingColumns = [
  { key: 'id', label: 'ID', width: '60px' },
  { key: 'type', label: '单据类型', slot: true, width: '140px' },
  { key: 'template', label: '模板', slot: true, width: '80px' },
  { key: 'priority', label: '优先级', slot: true, width: '80px' },
  { key: 'default', label: '默认', slot: true, width: '70px' },
  { key: 'active', label: '状态', slot: true, width: '90px' },
  { key: 'condition', label: '条件', slot: true, width: '180px' },
  { key: 'actions', label: '操作', slot: true, width: '140px' }
]

async function loadBindings() {
  if (!bindFilters.bo_code) {
    bindings.value = []
    return
  }
  bindLoading.value = true
  try {
    const response = await fetchBindings(bindFilters.bo_code, bindFilters.type_code || undefined)
    bindings.value = response.success ? (response.data || []) : []
  } catch (error) {
    message.error('绑定列表加载失败', error)
  } finally {
    bindLoading.value = false
  }
}

async function loadBindingTemplates() {
  if (!bindFilters.bo_code) {
    bindingTemplateOptions.value = []
    return
  }
  try {
    const response = await fetchTemplates({ bo_code: bindFilters.bo_code, page_size: 200 })
    bindingTemplateOptions.value = response.success ? (response.data || []) : []
  } catch {
    bindingTemplateOptions.value = []
  }
}

function handleBindBoChange() {
  bindFilters.type_code = ''
  loadBindings()
  loadBindingTemplates()
}

const bindingVisible = ref(false)
const bindingEditingId = ref(null)
const bindingSaving = ref(false)
const bindingForm = reactive({
  bo_code: '', type_code: '', template_id: null, priority: 100,
  is_default: false, is_active: true, condition_text: '{}',
  scope_type: 'system', scope_id: ''
})

function openCreateBinding() {
  bindingEditingId.value = null
  Object.assign(bindingForm, {
    bo_code: bindFilters.bo_code,
    type_code: bindFilters.type_code || '',
    template_id: null,
    priority: 100,
    is_default: false,
    is_active: true,
    condition_text: '{}',
    scope_type: 'system',
    scope_id: ''
  })
  bindingVisible.value = true
}

function openEditBinding(row) {
  bindingEditingId.value = row.id
  Object.assign(bindingForm, {
    bo_code: row.bo_code,
    type_code: row.type_code || '',
    template_id: row.template_id,
    priority: row.priority,
    is_default: Boolean(row.is_default),
    is_active: Boolean(row.is_active),
    condition_text: JSON.stringify(row.condition || {}),
    scope_type: row.scope_type || 'system',
    scope_id: row.scope_id || ''
  })
  bindingVisible.value = true
}

async function saveBinding() {
  if (!bindingForm.template_id) {
    message.error('请选择模板')
    return
  }
  let condition
  try {
    condition = JSON.parse(bindingForm.condition_text || '{}')
  } catch {
    message.error('条件 JSON 解析失败')
    return
  }
  const payload = {
    bo_code: bindingForm.bo_code,
    type_code: bindingForm.type_code || '',
    template_id: bindingForm.template_id,
    priority: Number(bindingForm.priority) || 100,
    is_default: bindingForm.is_default ? 1 : 0,
    is_active: bindingForm.is_active ? 1 : 0,
    condition,
    scope_type: bindingForm.scope_type,
    scope_id: bindingForm.scope_id || null
  }
  bindingSaving.value = true
  try {
    const response = bindingEditingId.value
      ? await updateBinding(bindingEditingId.value, payload)
      : await createBinding(payload)
    if (!response.success) {
      message.error(response.message || '保存失败')
      return
    }
    message.success(bindingEditingId.value ? '绑定已保存' : '绑定已创建')
    bindingVisible.value = false
    await loadBindings()
  } catch (error) {
    message.error('保存失败', error)
  } finally {
    bindingSaving.value = false
  }
}

async function handleDeleteBinding(row) {
  const confirmed = await message.confirm({
    title: '停用绑定',
    content: '停用后该绑定不再参与模板命中，历史打印记录不受影响。确认停用？',
    type: 'warning'
  })
  if (!confirmed) return
  try {
    const response = await deleteBinding(row.id)
    if (!response.success) {
      message.error(response.message || '停用失败')
      return
    }
    message.success('绑定已停用')
    await loadBindings()
  } catch (error) {
    message.error('停用失败', error)
  }
}

// ------------------------------------------------------------------ 试算

const resolveForm = reactive({ bo_code: '', type_code: '', doc_id: '' })
const resolveLoading = ref(false)
const resolveResult = ref(null)
const resolveTypeOptions = computed(() => typeOptionsOf(resolveForm.bo_code))
const resolveSummaryText = computed(() => (
  resolveResult.value ? JSON.stringify(resolveResult.value, null, 2) : ''
))

async function handleResolve() {
  if (!resolveForm.bo_code || !resolveForm.doc_id) {
    message.error('请填写业务对象与单据 ID')
    return
  }
  resolveLoading.value = true
  try {
    const response = await resolveTemplate({
      bo_code: resolveForm.bo_code,
      type_code: resolveForm.type_code || '',
      doc_id: resolveForm.doc_id
    })
    if (!response.success) {
      message.error(response.message || '试算失败')
      resolveResult.value = null
      return
    }
    resolveResult.value = response.data
  } catch (error) {
    message.error('试算失败', error)
  } finally {
    resolveLoading.value = false
  }
}

// ------------------------------------------------------------------ 初始化

async function loadPrintable() {
  try {
    const response = await fetchPrintable()
    if (!response.success) {
      loadError.value = response.message || '可打印清单加载失败'
      return
    }
    printable.value = response.data || []
  } catch {
    loadError.value = '可打印清单加载失败'
  }
}

async function reloadAll() {
  loading.value = true
  loadError.value = ''
  try {
    await loadPrintable()
    if (!tplFilters.bo_code && boOptions.value.length) {
      tplFilters.bo_code = boOptions.value[0].bo_code
      bindFilters.bo_code = boOptions.value[0].bo_code
      resolveForm.bo_code = boOptions.value[0].bo_code
    }
    await Promise.all([loadTemplates(), loadBindings(), loadBindingTemplates()])
  } finally {
    loading.value = false
  }
}

onMounted(reloadAll)
</script>

<style scoped>
.print-admin {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.print-admin__tabs {
  background: var(--color-bg-primary);
  border: var(--border-width-thin) solid var(--color-border-secondary);
  border-radius: var(--radius-md);
  padding: 4px 16px 16px;
}
.print-admin__filters {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 4px 0 12px;
}
.print-admin__hint {
  color: var(--color-text-secondary);
  font-size: 12px;
}
.print-admin__cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.print-admin__strong {
  font-weight: 600;
}
.print-admin__muted {
  color: var(--color-text-secondary);
  font-size: 12px;
}
.print-admin__badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 12px;
  border: var(--border-width-thin) solid transparent;
}
.print-admin__badge--success {
  color: var(--color-success);
  background: var(--color-success-bg, rgba(22, 163, 74, 0.12));
}
.print-admin__badge--warning {
  color: var(--color-warning);
  background: var(--color-warning-bg, rgba(217, 119, 6, 0.12));
}
.print-admin__badge--danger {
  color: var(--color-danger);
  background: var(--color-danger-bg, rgba(220, 38, 38, 0.12));
}
.print-admin__badge--muted {
  color: var(--color-text-secondary);
  background: var(--color-bg-secondary);
}
.print-admin__actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}
.print-admin__form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.print-admin__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.print-admin__grid--two {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.print-admin__margins {
  display: flex;
  align-items: center;
  gap: 8px;
}
.print-admin__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.print-admin__field label {
  font-size: 12px;
  color: var(--color-text-secondary);
}
.print-admin__code :deep(textarea) {
  font-family: var(--font-family-mono, Consolas, Monaco, monospace);
  font-size: 12px;
  line-height: 1.5;
}
.print-admin__footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.print-admin__json {
  margin: 12px 0 0;
  padding: 12px;
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  font-size: 12px;
  line-height: 1.5;
  max-height: 420px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>