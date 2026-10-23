<template>
  <div class="generic-tab-container">
    <!-- [单 tab 不渲染二级导航 2026-10-17] 单页 hub（page_type=multi_object_hub 且无 children，
         isSelfPage 分支 L99-100）时 tabs 恒为 1 项，SubNavTabs 退化成不可切换的单选控件：
         既无导航作用，又占一整行，且标签常与内层 MOMP tab 组首项同名
         （用户手机端报障：往来单位页「往来单位」标题与下方 tab 组首项重复出现）。
         故 tabs.length === 1 时整块不渲染，内容区直接占满（.gtc-content flex:1）。
         影响面仅限 GenericTabContainer 侧单 tab 的组：party-management / material-management /
         business-config；多 tab 的 user-permission、master-data 不受影响。
         注：SubNavTabs 组件本身保留 —— TaskCenter.vue:3 是独立消费方。
         内容区渲染不依赖 SubNavTabs（各分支只判 isCustomComponent / tab.objectType / activeTab），
         故跳过 nav 不影响内容。 -->
    <SubNavTabs
      v-if="visibleTabs.length > 1"
      :tabs="visibleTabs"
      :model-value="activeTab"
      :aria-label="title"
      @update:model-value="handleTabChange"
    />

    <div class="gtc-content">
      <template v-for="tab in allTabs" :key="tab.key">
        <slot
          v-if="$slots[`tab-${tab.key}`]"
          :name="`tab-${tab.key}`"
          :tab="tab"
        />
        <component
          v-else-if="isCustomComponent(tab.key) && shouldRender(tab.key)"
          v-show="activeTab === tab.key"
          :is="resolvedComponents[tab.key]"
        />
        <GenericObjectList
          v-else-if="tab.objectType && shouldRender(tab.key)"
          v-show="activeTab === tab.key"
          :object-type="tab.objectType"
          v-bind="tab.props || {}"
          @detail="(payload) => $emit('detail', { tab: tab.key, ...payload })"
          @action="(payload) => $emit('action', { tab: tab.key, ...payload })"
        />
      </template>
    </div>

    <slot name="after" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onActivated, markRaw } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { useTabStore } from '@/stores/tabStore'
import { SubNavTabs } from '@/components/common'
import GenericObjectList from '@/views/GenericObjectList.vue'
import { useMenuPermissions } from '@/composables/useMenuPermissions'
import { getGroupTabs, getGroupTitle } from '@/config/menuConfig'

const props = defineProps({
  group: {
    type: String,
    required: true
  }
})

defineEmits(['detail', 'action'])

defineOptions({ name: 'GenericTabContainer' })

const route = useRoute()
const router = useRouter()
const { accessibleMenus, loadMenuPermissions } = useMenuPermissions()

const USE_API_MENU = true
const menuLoaded = ref(false)

const apiMenuNode = computed(() => {
  const menus = accessibleMenus.value
  if (!menus || !menus.length) return null

  const findNode = (nodes, code) => {
    for (const n of nodes) {
      if (n.menu_code === code) return n
      if (n.children && n.children.length) {
        const found = findNode(n.children, code)
        if (found) return found
      }
    }
    return null
  }
  return findNode(menus, props.group)
})

const apiTitle = computed(() => {
  if (!menuLoaded.value) return null
  return apiMenuNode.value?.menu_name || null
})

const apiTabs = computed(() => {
  if (!menuLoaded.value) return null
  const node = apiMenuNode.value
  if (!node) return null
  const children = node.children || []
  // [FIX 2026-10-11] 无 children 时把节点自身当作唯一 tab。
  //   背景: multi_object_hub 菜单有两种形态 ——
  //     (a) 聚合容器 (user-permission / master-data): 有 children, children 即 tabs
  //     (b) 单页hub (material-management): 无 children, 自己就是要渲染的那一页
  //   原实现只认 (a), (b) 时 apiTabs=null → 落到 getGroupTabs 配置兜底 → 配置里没有
  //   该 menu_code → 空容器 (tab 标题渲染了但内容空白, 用户实测)。
  //   注: org-management 不受影响, 它在 router/modules/business.js 有静态路由直连
  //   OrgManagement.vue, 不经本容器。
  const isSelfPage = children.length === 0
  const list = isSelfPage ? [node] : children
  return list.map(child => ({
    key: child.menu_code,
    label: child.menu_name,
    // [FIX 2026-10-14 单页 hub 空白] 原判定只看 page_type === 'object_list'，
    // 但 multi_object_hub 也可能「无 children + 自己带 primary_object_type」——
    // 后端 business-config 就是这个形态 (type=multi_object_hub, pot=enum_type,
    // kids=0)。此前 objectType 被置 null，而它又没有显式 component 映射，
    // 模板里 isCustomComponent 与 tab.objectType 两个分支同时落空，
    // .gtc-content 只剩一个 <!--v-if--> 注释 → 页签标题渲染了、内容整页空白
    // （PC 与窄屏同症，非响应式问题）。
    // 条件: 叶子 object_list，或「自身即页面」的 hub（isSelfPage）。
    // 非自页 hub（arch-data / master-data 等有 children 的）仍须走 children 分支，
    // 它们渲染的是聚合视图而非单个对象列表。
    objectType: (child.page_type === 'object_list' || isSelfPage)
      ? child.primary_object_type
      : null,
    pageType: child.page_type,
    objectTypes: child.object_types,
  }))
})

const title = computed(() => {
  if (USE_API_MENU && apiTitle.value) return apiTitle.value
  return getGroupTitle(props.group)
})

// [2026-08-30 Spec16] "组织管理"为 user-permission 组下的子 tab（menu_code=org-management）。
// 它是 multi_object_hub 页面类型（非 object_list），需用组件渲染而非 GenericObjectList，
// 因此精确映射该 tab 渲染 OrgManagement.vue（MOMP 泛化页）。
const ORG_MANAGEMENT_LOADER = () => import('@/views/SystemManagement/OrgManagement.vue')

// [2026-10-11] "物料管理"是 master-data 组下的子菜单（menu_code=material-management）。
// 同样是 multi_object_hub 页面类型，但渲染的是 MaterialManagement.vue ——
// 左树注入物料组树、右表物料，MOMP 泛化页。与组织管理页同构的映射方式。
const MATERIAL_MANAGEMENT_LOADER = () => import('@/views/MasterData/MaterialManagement.vue')

// [2026-10-11] "往来单位"同为 master-data 组下的单页 hub（menu_code=party-management），
// 渲染 PartyManagement.vue —— 左树注入往来单位组树、右表往来单位/往来单位组两个 tab。
// 与物料管理的差异: party 不直挂 group, 左树→右表的过滤在 PartyManagement 内做两段桥接。
const PARTY_MANAGEMENT_LOADER = () => import('@/views/MasterData/PartyManagement.vue')

// [2026-10-23] "位置管理"原为自动生成的 object_list 菜单（location-list），
// 与组织/物料不一致（无左侧树）。改为单页 hub 后渲染 LocationManagement.vue ——
// 左树注入位置树（site/warehouse/zone/bin），右表位置列表。映射方式同物料管理。
const LOCATION_MANAGEMENT_LOADER = () => import('@/views/MasterData/LocationManagement.vue')

function decorateComponentTab(tab) {
  if (tab.key === 'org-management' || tab.menu_code === 'org-management') {
    return { ...tab, component: ORG_MANAGEMENT_LOADER }
  }
  if (tab.key === 'material-management' || tab.menu_code === 'material-management') {
    return { ...tab, component: MATERIAL_MANAGEMENT_LOADER }
  }
  if (tab.key === 'party-management' || tab.menu_code === 'party-management') {
    return { ...tab, component: PARTY_MANAGEMENT_LOADER }
  }
  if (tab.key === 'location-list' || tab.menu_code === 'location-list') {
    return { ...tab, component: LOCATION_MANAGEMENT_LOADER }
  }
  return tab
}

const allTabs = computed(() => {
  if (USE_API_MENU && menuLoaded.value && apiTabs.value && apiTabs.value.length > 0) {
    return apiTabs.value.map(decorateComponentTab)
  }

  const configTabs = getGroupTabs(props.group)
  return configTabs.map(t => ({
    ...t,
    key: t.key || t.menu_code,
    label: t.label || t.menu_name,
  })).map(decorateComponentTab)
})

const resolvedComponents = ref({})

const visibleTabs = computed(() => {
  return allTabs.value.filter(tab => {
    if (typeof tab.visible === 'function') {
      return tab.visible({ route, query: route.query })
    }
    return tab.visible !== false
  })
})

function isCustomComponent(key) {
  const tab = allTabs.value.find(t => t.key === key)
  return !!(tab?.component && resolvedComponents.value[key])
}

const activeTab = ref(getInitialTab())

// [NFR-009] 懒加载：仅渲染已访问过的 tab，避免一次性创建所有 tab 的组件实例
// 使用 reactive(new Set()) 确保 Set.add() 触发 Vue 响应式更新
const visitedTabs = reactive(new Set([activeTab.value || getInitialTab()]))

function getInitialTab() {
  const paramTab = route.params.tab
  const queryTab = route.query.tab

  if (paramTab && allTabs.value.find(t => t.key === paramTab)) {
    return paramTab
  }
  if (queryTab && allTabs.value.find(t => t.key === queryTab)) {
    return queryTab
  }
  return allTabs.value[0]?.key || ''
}

function handleTabChange(key) {
  activeTab.value = key
  visitedTabs.add(key)
  // [FIX 2026-06-19] 改用 path param (如 /user-permission/roles), 不是 query (?tab=roles)
  //   原因: query 形式在 tabStore 持久化 + API 菜单加载完成后会失效
  //   (API menu_code 与静态 key 不一致导致 fallback 到默认 subtab)
  //   path param 是 deep link 友好, 符合头部产品语义 (GitHub, Slack)
  if (route.params.tab !== key) {
    router.replace({ params: { ...route.params, tab: key } })
  }
}

// [NFR-009] 判断 tab 是否应该渲染 DOM
function shouldRender(key) {
  return visitedTabs.has(key)
}

watch(allTabs, (tabs) => {
  tabs.forEach(tab => {
    if (tab.component && !resolvedComponents.value[tab.key]) {
      tab.component().then(mod => {
        resolvedComponents.value[tab.key] = markRaw(mod.default || mod)
      })
    }
  })

  const needsReset = !activeTab.value || activeTab.value === '' || !tabs.find(t => t.key === activeTab.value)
  if (tabs.length > 0 && needsReset) {
    const newKey = tabs[0].key || ''
    activeTab.value = newKey
    // [FIX 2026-06-20] 同步 visitedTabs, 否则 shouldRender 返回 false, tab 内容不渲染
    if (newKey) visitedTabs.add(newKey)
  }
}, { immediate: true })

onMounted(async () => {
  await loadMenuPermissions()
  menuLoaded.value = true
  const tab = getInitialTab()
  if (tab && tab !== activeTab.value) {
    activeTab.value = tab
    // [FIX 2026-06-20] 同步 visitedTabs, 否则 shouldRender 返回 false, tab 内容不渲染
    visitedTabs.add(tab)
  }
})

// [FR-005] 路由切换回来时，刷新当前激活 tab 的数据
onActivated(() => {
  // [FR-005] SAP Fiori iAppState 模式：路由切回时保留状态，不自动刷新
  // 数据变更由 refreshCoordinator 处理
})

onBeforeRouteLeave((_to, _from) => {
  const tabStore = useTabStore()
  const tabEntry = tabStore.tabs.find(t => t.id === route.path)
  if (tabEntry && tabEntry.path !== route.fullPath) {
    tabStore.closeTab(route.path)
    tabStore.openTab({
      id: route.path,
      label: tabEntry.label,
      path: route.fullPath,
      icon: tabEntry.icon,
      badge: tabEntry.badge,
      closable: tabEntry.closable,
      pinned: tabEntry.pinned,
      meta: tabEntry.meta
    })
    tabStore.switchTab(route.path)
  }
})
</script>

<style scoped>
.generic-tab-container {
  /* [FIX 2026-06-20] flex:1 替代 height:100% */
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-layout);
}

.gtc-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: var(--spacing-md);
  min-height: 0;
}

/* [窄屏内边距 2026-10-17] 移动端 padding 16 → 8。
 *   报障：页签栏（app-tabs）与页面卡片之间有一条约 24px 的灰带，看着像多余空白
 *     （用户手机端圈出反馈）。实测构成（390x844）：app-shell__content 的 padding-top:8px
 *     + 本元素 padding:16px（--spacing-md），两段相加 = 24px，露出的是 layout 底色。
 *   为什么只在窄屏改：16px 是照桌面端定的 —— 桌面端页签栏/工具栏本身有分隔，
 *     卡片四周留宽一点不显空；移动端 390px 宽，24px 四边合计吃掉 12% 屏宽，
 *     且列表/卡片内容被迫更早换行。业界移动端页面级留白普遍 8–12px
 *     （Material 8dp、SAP Fiori 移动版 12px），故取 8px。
 *   影响面：所有走本容器的页面（往来单位 / 物料 / 业务配置 / 用户权限 / 主数据…）
 *     的**移动端**内边距一起变小；桌面端不受影响。
 *   副作用（预期内）：卡片宽度增加约 32px，内容少一次换行 —— 移动端这是净收益。
 *   功能零影响：纯布局留白，不涉及任何逻辑、交互与数据。 */
@media (max-width: 768px) {
  .gtc-content {
    padding: var(--spacing-sm);
  }
}
</style>
