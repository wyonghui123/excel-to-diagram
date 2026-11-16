<template>
  <PageShell
    title="集成连接"
    subtitle="配置面：渠道 / 鉴权 / 超时重试；订阅与投递共用同一份连接"
  >
    <AppCard title="连接列表">
      <div class="toolbar">
        <AppInput
          v-model="filters.keyword"
          size="sm"
          placeholder="搜索编码 / 名称 / 端点"
          class="w-260"
        />
        <AppSelect
          v-model="filters.channel_type"
          :options="channelOptions"
          size="sm"
          placeholder="全部渠道"
          clearable
          class="w-150"
        />
        <AppSelect
          v-model="filters.enabled"
          :options="enabledOptions"
          size="sm"
          placeholder="全部状态"
          clearable
          class="w-140"
        />
        <AppButton variant="secondary" size="sm" :loading="loading" @click="load">刷新</AppButton>
        <span class="spacer" />
        <AppButton variant="primary" size="sm" @click="openCreate">新建连接</AppButton>
      </div>

      <div v-if="error" class="alert">{{ error }}</div>
      <EmptyState
        v-else-if="!loading && !rows.length"
        type="empty"
        title="暂无连接"
        description="新建连接后即可被订阅与投递复用"
      />
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>编码</th>
              <th>名称</th>
              <th>渠道</th>
              <th>方向</th>
              <th>端点</th>
              <th>鉴权</th>
              <th>密钥</th>
              <th>超时 / 重试</th>
              <th>状态</th>
              <th>更新时间</th>
              <th class="col-action">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.code">
              <td class="mono">{{ row.code }}</td>
              <td>{{ row.name }}</td>
              <td>{{ row.channel_type }}</td>
              <td>{{ row.direction }}</td>
              <td class="mono ellipsis" :title="row.endpoint">{{ row.endpoint }}</td>
              <td>{{ row.auth_type }}</td>
              <td>
                <span :class="['tag', row.has_secret ? 'tag-on' : 'tag-off']">
                  {{ row.has_secret ? '已配置' : '未配置' }}
                </span>
              </td>
              <td class="mono">{{ row.timeout_ms }}ms / {{ row.retry_max }}</td>
              <td>
                <span :class="['tag', row.enabled ? 'tag-on' : 'tag-off']">
                  {{ row.enabled ? '启用' : '停用' }}
                </span>
              </td>
              <td class="mono">{{ row.updated_at }}</td>
              <td class="col-action">
                <AppButton variant="ghost" size="sm" :loading="testing === row.code" @click="handleTest(row)">
                  测试
                </AppButton>
                <AppButton variant="ghost" size="sm" @click="openEdit(row)">编辑</AppButton>
                <AppButton variant="ghost" size="sm" @click="handleDelete(row)">删除</AppButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppCard>

    <Drawer v-model="drawer" :title="editingCode ? '编辑连接' : '新建连接'" width="560px">
      <div class="form">
        <div class="form-row">
          <span class="form-label">编码 *</span>
          <AppInput v-model="form.code" :disabled="!!editingCode" placeholder="以字母开头，如 erp-prod" />
        </div>
        <div class="form-row">
          <span class="form-label">名称 *</span>
          <AppInput v-model="form.name" placeholder="如 ERP 生产环境" />
        </div>
        <div class="form-row">
          <span class="form-label">渠道 *</span>
          <AppSelect v-model="form.channel_type" :options="channelEditOptions" />
        </div>
        <div class="form-row">
          <span class="form-label">方向</span>
          <AppSelect v-model="form.direction" :options="directionOptions" />
        </div>
        <div class="form-row">
          <span class="form-label">端点 *</span>
          <AppInput v-model="form.endpoint" placeholder="https://..." />
        </div>
        <div class="form-row">
          <span class="form-label">鉴权</span>
          <AppSelect v-model="form.auth_type" :options="authOptions" />
        </div>
        <div class="form-row">
          <span class="form-label">密钥引用</span>
          <AppInput v-model="form.secret_ref" placeholder="env:ERP_TOKEN 或 vault:path/key" />
        </div>
        <div class="form-row">
          <span class="form-label">超时(ms)</span>
          <AppInput v-model.number="form.timeout_ms" type="number" />
        </div>
        <div class="form-row">
          <span class="form-label">最大重试</span>
          <AppInput v-model.number="form.retry_max" type="number" />
        </div>
        <div class="form-row">
          <span class="form-label">启用</span>
          <AppSelect v-model="form.enabled" :options="flagOptions" />
        </div>
        <p class="form-hint">密钥只接受引用（env: / vault:），不接受明文；留空表示无密钥。</p>
      </div>
      <template #footer>
        <div class="footer-actions">
          <AppButton variant="secondary" @click="drawer = false">取消</AppButton>
          <AppButton variant="primary" :loading="saving" @click="submit">保存</AppButton>
        </div>
      </template>
    </Drawer>
  </PageShell>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { PageShell, AppCard, AppButton, AppInput, AppSelect, Drawer, EmptyState } from '@/components/common'
import { useMessage } from '@/composables/useMessage'
import {
  fetchConnections, createConnection, updateConnection,
  deleteConnection, testConnection,
} from '@/services/integrationService'

defineOptions({ name: 'IntegrationConnections' })

const toast = useMessage()

const CHANNELS = ['webhook', 'rest', 'file', 'b2b']
const DIRECTIONS = ['outbound', 'inbound', 'both']
const AUTH_TYPES = ['none', 'api_key', 'basic', 'bearer', 'oauth2_cc', 'hmac']

const rows = ref([])
const loading = ref(false)
const saving = ref(false)
const testing = ref('')
const error = ref('')

const filters = reactive({ keyword: '', channel_type: '', enabled: '' })
const channelOptions = [{ value: '', label: '全部渠道' }, ...CHANNELS.map((v) => ({ value: v, label: v }))]
const enabledOptions = [{ value: '', label: '全部状态' }, { value: '1', label: '启用' }, { value: '0', label: '停用' }]
const channelEditOptions = CHANNELS.map((v) => ({ value: v, label: v }))
const directionOptions = DIRECTIONS.map((v) => ({ value: v, label: v }))
const authOptions = AUTH_TYPES.map((v) => ({ value: v, label: v }))
const flagOptions = [{ value: true, label: '启用' }, { value: false, label: '停用' }]

const drawer = ref(false)
const editingCode = ref('')
const form = reactive(emptyForm())

function emptyForm() {
  return {
    code: '', name: '', channel_type: 'rest', direction: 'outbound',
    endpoint: '', auth_type: 'none', secret_ref: '',
    timeout_ms: 15000, retry_max: 5, enabled: true,
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchConnections({
      keyword: filters.keyword || undefined,
      channel_type: filters.channel_type || undefined,
      enabled: filters.enabled === '' ? undefined : filters.enabled,
    })
    if (res.success) {
      rows.value = res.data?.items || []
    } else {
      error.value = res.message || '加载连接失败'
    }
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingCode.value = ''
  Object.assign(form, emptyForm())
  drawer.value = true
}

function openEdit(row) {
  editingCode.value = row.code
  Object.assign(form, {
    code: row.code, name: row.name, channel_type: row.channel_type,
    direction: row.direction, endpoint: row.endpoint, auth_type: row.auth_type,
    secret_ref: row.secret_ref || '', timeout_ms: row.timeout_ms,
    retry_max: row.retry_max, enabled: !!row.enabled,
  })
  drawer.value = true
}

async function submit() {
  if (!form.code.trim() || !form.name.trim() || !form.endpoint.trim()) {
    toast.warning('编码、名称、端点必填')
    return
  }
  saving.value = true
  try {
    const payload = { ...form }
    if (editingCode.value) {
      delete payload.code
      const res = await updateConnection(editingCode.value, payload)
      if (!res.success) {
        toast.error(res.message || '保存失败')
        return
      }
    } else {
      const res = await createConnection(payload)
      if (!res.success) {
        toast.error(res.message || '创建失败')
        return
      }
    }
    toast.success('已保存')
    drawer.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function handleTest(row) {
  testing.value = row.code
  try {
    const res = await testConnection(row.code)
    if (res.success) {
      const info = res.data || {}
      const okFlag = info.valid !== false
      toast[okFlag ? 'success' : 'warning'](
        `${okFlag ? '连通' : '不可用'}：${info.message || '已探测'}（${info.elapsed_ms ?? '-'}ms）`,
      )
    } else {
      toast.error(res.message || '测试失败')
    }
  } finally {
    testing.value = ''
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`删除连接「${row.code}」？被订阅 / 投递引用时会拒绝。`, '确认删除', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch {
    return
  }
  const res = await deleteConnection(row.code)
  if (res.success) {
    toast.success('已删除')
    await load()
  } else {
    const refs = res.data?.details?.refs || res.details?.refs
    toast.error(refs ? `${res.message}（引用：${JSON.stringify(refs)}）` : (res.message || '删除失败'))
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.spacer { flex: 1; }
.w-260 { width: 260px; }
.w-150 { width: 150px; }
.w-140 { width: 140px; }
.alert {
  padding: 10px 12px;
  border-radius: 6px;
  background: #fef2f2;
  color: #b91c1c;
  font-size: 13px;
}
.table-wrap { overflow-x: auto; }
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.data-table th,
.data-table td {
  padding: 9px 10px;
  text-align: left;
  border-bottom: 1px solid var(--border-color, #eef0f3);
  white-space: nowrap;
}
.data-table th {
  font-weight: 600;
  color: var(--text-secondary, #6b7280);
  background: var(--bg-subtle, #f9fafb);
}
.data-table .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.data-table .ellipsis { max-width: 240px; overflow: hidden; text-overflow: ellipsis; }
.col-action { text-align: right; }
.tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 12px;
}
.tag-on { background: #ecfdf5; color: #047857; }
.tag-off { background: #f3f4f6; color: #6b7280; }
.form { display: flex; flex-direction: column; gap: 12px; }
.form-row { display: flex; flex-direction: column; gap: 6px; }
.form-label { font-size: 12px; color: var(--text-secondary, #6b7280); }
.form-hint { font-size: 12px; color: var(--text-secondary, #6b7280); margin: 4px 0 0; }
.footer-actions { display: flex; justify-content: flex-end; gap: 8px; }
</style>