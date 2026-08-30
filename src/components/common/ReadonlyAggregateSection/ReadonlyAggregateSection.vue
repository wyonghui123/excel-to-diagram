<template>
  <div class="ras">
    <!-- 统计行 -->
    <div v-if="data && data.summary" class="ras__summary">
      有效 <strong>{{ data.summary.permission_set_count }}</strong> 个权限集
      <template v-if="isOrg">（本组织直挂 {{ data.summary.direct_count }} / 父级继承 {{ data.summary.inherited_count }}）</template>
      <template v-else>（来源组织 {{ data.summary.source_org_count }} 个）</template>
    </div>

    <!-- 加载 -->
    <div v-if="loading" class="ras__loading">加载中...</div>

    <!-- 错误 + 重试 -->
    <div v-else-if="error" class="ras__error">
      <p>{{ error }}</p>
      <button class="ras__retry" @click="load">重试</button>
    </div>

    <!-- 空态 -->
    <div v-else-if="data && data.permission_sets.length === 0" class="ras__empty">
      该组织未配置权限，且无父级继承
    </div>

    <!-- 主体 -->
    <template v-else-if="data">
      <!-- 功能权限卡片 -->
      <div class="ras__sets">
        <div v-for="ps in data.permission_sets" :key="ps.permission_set_id" class="ras__card">
          <div class="ras__card-head" @click="toggle(ps.permission_set_id)">
            <span class="ras__card-name">{{ ps.permission_set_name }}</span>
            <span class="ras__card-code">{{ ps.permission_set_code }}</span>
            <span v-if="ps.is_system" class="ras__tag">系统</span>
            <span v-for="s in ps.source_orgs" :key="s.org_id" class="ras__src">{{ s.org_name }}</span>
            <span v-if="!ps.granted" class="ras__exclude">排除</span>
          </div>
          <div v-if="expanded[ps.permission_set_id]" class="ras__perms">
            <div v-for="p in ps.permissions" :key="p.permission_id" class="ras__perm">
              <span>{{ p.permission_name }}（{{ p.permission_code }}）</span>
              <span v-if="!p.granted" class="ras__exclude">排除</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 数据权限资源聚合表 -->
      <table v-if="data.data_permissions.length > 0" class="ras__table">
        <thead>
          <tr>
            <th>资源类型</th><th>资源</th><th>权限级别</th><th>继承至子级</th><th>来源</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(dp, i) in data.data_permissions" :key="i">
            <td>{{ dp.resource_type }}</td>
            <td>{{ dp.resource_id }}</td>
            <td>{{ dp.permission_level }}</td>
            <td>{{ dp.inherit_to_children ? '是' : '否' }}</td>
            <td class="ras__src-cell">
              <span class="ras__src-trigger" @click="toggleSource(i)">查看来源 ({{ dp.sources.length }})</span>
              <div v-if="hoverSource === i" class="ras__tooltip">
                <div v-for="(s, si) in dp.sources" :key="si" class="ras__tooltip-item">
                  {{ s.org_name }} › {{ s.permission_set_name }}
                </div>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else-if="data.data_permissions.length === 0 && data.permission_sets.length > 0" class="ras__empty">无数据权限</div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { apiV1 } from '@/utils/httpClient'

const props = defineProps({
  endpoint: { type: String, default: '' },   // 由元数据 config 注入，如 /orgs/{id}/permission-preview（id 已插值；/api/v1 前缀会被归一化）
  fetchFn: { type: Function, default: null }, // 可注入的拉取函数（默认用 apiV1.get）
})
const emit = defineEmits(['loaded'])

const data = ref(null)
const loading = ref(false)
const error = ref('')
const expanded = ref({})
const hoverSource = ref(-1)

const isOrg = computed(() => (props.endpoint || '').includes('/orgs/'))

async function load() {
  loading.value = true
  error.value = ''
  try {
    let endpoint = props.endpoint
    if (endpoint.startsWith('/api/v1')) endpoint = endpoint.replace('/api/v1', '')
    const resp = props.fetchFn
      ? await props.fetchFn(props.endpoint)
      : await apiV1.get(endpoint)
    if (resp.success) {
      data.value = resp.data
      emit('loaded', resp.data)
    } else {
      error.value = resp.message || '加载失败'
    }
  } catch (e) {
    error.value = String(e?.message || e)
  } finally {
    loading.value = false
  }
}
function toggle(id) {
  expanded.value[id] = !expanded.value[id]
}
function toggleSource(i) {
  hoverSource.value = hoverSource.value === i ? -1 : i
}

onMounted(load)
</script>

<style scoped>
.ras__summary { margin-bottom: 12px; font-size: 14px; color: #333; }
.ras__loading, .ras__empty, .ras__error { padding: 16px; color: #888; }
.ras__retry { margin-left: 8px; cursor: pointer; }
.ras__sets { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.ras__card { border: 1px solid #e3e6eb; border-radius: 6px; padding: 8px 12px; }
.ras__card-head { display: flex; gap: 8px; align-items: center; cursor: pointer; flex-wrap: wrap; }
.ras__card-name { font-weight: 600; }
.ras__card-code { color: #999; font-size: 12px; }
.ras__tag { background: #f0f2f5; color: #555; padding: 0 6px; border-radius: 4px; font-size: 12px; }
.ras__src { background: #e6f7ff; color: #0958d9; padding: 0 6px; border-radius: 4px; font-size: 12px; }
.ras__exclude { color: #cf1322; font-size: 12px; }
.ras__perms { margin-top: 8px; padding-left: 8px; border-left: 2px solid #e3e6eb; }
.ras__perm { padding: 2px 0; font-size: 13px; color: #555; }
.ras__table { width: 100%; border-collapse: collapse; }
.ras__table th, .ras__table td { border: 1px solid #e3e6eb; padding: 6px 8px; text-align: left; font-size: 13px; }
.ras__src-cell { position: relative; }
.ras__src-trigger { cursor: pointer; color: #0958d9; }
.ras__tooltip { position: absolute; background: #fff; border: 1px solid #e3e6eb; box-shadow: 0 2px 8px rgba(0,0,0,.12); padding: 6px 8px; z-index: 10; min-width: 160px; }
.ras__tooltip-item { font-size: 12px; color: #555; }
</style>