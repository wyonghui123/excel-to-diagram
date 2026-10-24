<template>
  <MultiObjectManagementPage
    v-if="resolved"
    ref="pageRef"
    :object-types="resolved.objectTypes"
    :options="resolved.options"
    @toolbar-action="handleToolbarAction"
  />
  <!-- 未声明 ui_view_config.hub 的单页 hub（架构数据 / 定价 / 业务配置等）保持原行为：
       直接一个对象列表，与改造前 GenericTabContainer 的通用分支等价 -->
  <GenericObjectList v-else-if="ready" :object-type="objectType" />
  <div v-else class="hub-loading">
    <el-icon class="is-loading" :size="20"><Loading /></el-icon>
  </div>
</template>

<script setup>
/**
 * MultiObjectHubPage — 单页 hub 的通用渲染器
 *
 * 取代「一对象一个 Vue 壳」（MaterialManagement / RegionManagement / LocationManagement /
 * PartyManagement / CalendarManagement / OrgManagement 六份近乎同构的壳）。页面形态全部来自对象 YAML 的
 * ui_view_config.hub，本组件只负责取配置 + 交给 MOMP，不含任何对象类型硬编码。
 *
 * - 有 hub 声明 → MultiObjectManagementPage（左树 + 多 tab）
 * - 无 hub 声明 → GenericObjectList(objectType)，行为与改造前一致
 *
 * 取配置走 metaService（v2 /meta/<obj>/ui-config，10 分钟缓存），primary_object_type
 * 即被查对象（物料页 = item、计量单位页 = uom）。
 */
import { ref, reactive, watch, onMounted } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { MultiObjectManagementPage } from '@/components/common/MultiObjectManagementPage'
import GenericObjectList from '@/views/GenericObjectList.vue'
import { metaService } from '@/services/metaService'
import { boService } from '@/services/boService'
import { resolveHubOptions } from './hubOptions'

defineOptions({ name: 'MultiObjectHubPage' })

const props = defineProps({
  // 被查 ui-config 的对象（菜单 primary_object_type）
  objectType: { type: String, required: true },
  // 菜单声明的 object_types，仅在 hub 缺失时作诊断参考，不参与渲染决策
  objectTypes: { type: Array, default: () => [] },
  menuCode: { type: String, default: '' }
})

const ready = ref(false)
const resolved = ref(null)
const pageRef = ref(null)

// 桥接结果（objectType → null | string[]）：null = 未选范围（全量）；[] = 选中但无关联（空集哨兵）
const bridgeIds = reactive({})
const bridges = ref([])
let bridgeSeq = 0

async function loadHubConfig() {
  if (!props.objectType) {
    ready.value = true
    return
  }
  ready.value = false
  resolved.value = null
  bridges.value = []
  Object.keys(bridgeIds).forEach((key) => { delete bridgeIds[key] })
  try {
    const result = await metaService.getUIConfig(props.objectType)
    const hub = result?.success ? result.data?.ui_view_config?.hub : null
    if (hub && Object.keys(hub).length) {
      const resolvedHub = resolveHubOptions(hub, { menuCode: props.menuCode, bridgeIds })
      if (resolvedHub) {
        bridges.value = resolvedHub.bridges || []
        resolved.value = resolvedHub
      }
    }
  } catch (error) {
    // 取不到配置不是致命错误：回退通用列表，页面至少可用
    console.warn(`[MultiObjectHubPage] ${props.objectType} 读取 hub 配置失败，回退通用列表:`, error)
  } finally {
    ready.value = true
  }
}

/**
 * 桥接执行器：树勾选 → 中间 BO 查询 → 取出目标集合
 *
 * 为什么监听 scopeIds 而不是只靠 scopeAdapter：
 *   MOMP 从图表/详情切回时 restoreStateFromDiagram 会直接写 scopeIds（不触发 scope-change），
 *   只挂在 adapter 上的桥接会让「树恢复了勾选、右表却是全量」。监听 scopeIds 后，
 *   用户勾选与状态恢复收敛到同一条管线。
 * 比较 join 字符串避免 adapter 反复写相同内容触发重复查询。
 */
async function runBridges() {
  const page = pageRef.value?.page
  if (!page || !bridges.value.length) return
  const seq = ++bridgeSeq
  for (const bridge of bridges.value) {
    const ids = page.scopeIds?.[bridge.scopeKey]?.effective || []
    if (!ids.length) {
      bridgeIds[bridge.objectType] = null
      continue
    }
    try {
      const res = await boService.query(bridge.through, {
        [`${bridge.matchField}__in`]: ids.join(','),
        page_size: bridge.pageSize
      })
      if (seq !== bridgeSeq) return // 快速连点: 只认最后一次
      const data = res?.data || res
      const items = data?.items || (Array.isArray(data) ? data : [])
      const collected = [...new Set(items.map((r) => r[bridge.collectField]).filter((v) => v != null))]
      bridgeIds[bridge.objectType] = collected
    } catch (error) {
      if (seq !== bridgeSeq) return
      // 失败不隐藏数据（宁可全量, 不误显空集）
      console.warn(`[MultiObjectHubPage] 桥接查询 ${bridge.through} 失败, 回退全量:`, error)
      bridgeIds[bridge.objectType] = null
    }
  }
}

watch(
  () => bridges.value.map((b) =>
    `${b.objectType}:${(pageRef.value?.page?.scopeIds?.[b.scopeKey]?.effective || []).join(',')}`
  ).join('|'),
  () => runBridges(),
  { immediate: true }
)

onMounted(loadHubConfig)
watch(() => props.objectType, loadHubConfig)

function handleToolbarAction(action) {
  const actionType = typeof action === 'string' ? action : action?.type
  if (actionType === 'refresh') {
    pageRef.value?.refresh?.()
  }
}

defineExpose({ refresh: () => pageRef.value?.refresh?.() })
</script>

<style scoped>
.hub-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-tertiary);
}
</style>
