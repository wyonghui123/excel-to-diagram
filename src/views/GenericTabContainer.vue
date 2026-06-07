<template>
  <div class="generic-tab-container">
    <SubNavTabs
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
          v-else-if="isCustomComponent(tab.key)"
          :is="resolvedComponents[tab.key]"
          v-if="activeTab === tab.key"
        />
        <GenericObjectList
          v-else-if="tab.objectType"
          v-if="activeTab === tab.key"
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
import { ref, computed, watch, onMounted, onBeforeUnmount, markRaw } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { useTabStore } from '@/stores/tabStore'
import { SubNavTabs } from '@/components/common'
import GenericObjectList from '@/views/GenericObjectList.vue'
import { useMenuPermissions } from '@/composables/useMenuPermissions'
import { tabGroupConfigs, getGroupTabs, getGroupTitle } from '@/config/menuConfig'

const props = defineProps({
  group: {
    type: String,
    required: true
  }
})

defineEmits(['detail', 'action'])

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
  if (!apiMenuNode.value?.children || apiMenuNode.value.children.length === 0) return null
  return apiMenuNode.value.children.map(child => ({
    key: child.menu_code,
    label: child.menu_name,
    objectType: child.page_type === 'object_list' ? child.primary_object_type : null,
    pageType: child.page_type,
    objectTypes: child.object_types,
  }))
})

const title = computed(() => {
  if (USE_API_MENU && apiTitle.value) return apiTitle.value
  return getGroupTitle(props.group)
})

const allTabs = computed(() => {
  if (USE_API_MENU && menuLoaded.value && apiTabs.value && apiTabs.value.length > 0) {
    return apiTabs.value
  }

  const configTabs = getGroupTabs(props.group)
  return configTabs.map(t => ({
    ...t,
    key: t.key || t.menu_code,
    label: t.label || t.menu_name,
  }))
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
  if (route.query.tab !== key) {
    router.replace({ query: { ...route.query, tab: key } })
  }
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
    activeTab.value = tabs[0].key || ''
  }
}, { immediate: true })

onMounted(async () => {
  await loadMenuPermissions()
  menuLoaded.value = true
  const tab = getInitialTab()
  if (tab && tab !== activeTab.value) {
    activeTab.value = tab
  }
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
  height: 100%;
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
</style>
