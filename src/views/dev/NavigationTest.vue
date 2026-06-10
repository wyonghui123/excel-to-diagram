<template>
  <AppLayout
    :show-sidebar="true"
    :show-tabs="true"
    :sidebar-items="menuItems"
    :sidebar-active="activeMenuItem"
    :breadcrumbs="breadcrumbs"
    :search-suggestions="searchSuggestions"
    :recent-searches="recentSearches"
    @logo-click="handleLogoClick"
    @notification-click="handleNotificationClick"
    @search="handleSearch"
    @suggestion-click="handleSuggestionClick"
    @user-command="handleUserCommand"
    @tab-change="handleTabChange"
    @tab-close="handleTabClose"
    @sidebar-select="handleSidebarSelect"
    @sidebar-collapse="handleSidebarCollapse"
    @ai-click="handleAIClick"
    @favorites-click="handleFavoritesClick"
    @recent-click="handleRecentClick"
  >
    <div class="navigation-test">
      <el-row :gutter="16">
        <el-col :span="24">
          <el-alert
            title="侧边栏完全隐藏 - 点击顶部左侧汉堡菜单按钮展开"
            type="success"
            show-icon
            :closable="false"
            style="margin-bottom: 16px"
          >
            <template #default>
              <span>点击顶部左侧的菜单按钮或使用键盘快捷键展开侧边栏</span>
            </template>
          </el-alert>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-card class="test-card">
            <template #header>
              <div class="card-header">
                <span>AI 智能化功能演示</span>
              </div>
            </template>

            <div class="feature-section">
              <h4>多 Tab 上下文追踪</h4>
              <p class="description">
                AI 可以追踪用户在多个 Tab 中的操作，理解跨任务的工作上下文。
              </p>
              <el-space wrap>
                <el-button @click="openDataTab">
                  打开 Tab: 数据管理
                </el-button>
                <el-button @click="openDiagramTab">
                  打开 Tab: 架构图
                </el-button>
                <el-button @click="openReportTab">
                  打开 Tab: 报表
                </el-button>
              </el-space>

              <el-divider />

              <h4>收藏夹功能</h4>
              <p class="description">
                快速访问常用功能，AI 会学习您的使用习惯。
              </p>
              <div class="favorites-list">
                <div
                  v-for="item in favorites"
                  :key="item.id"
                  class="favorite-item"
                >
                  <AppIcon :name="item.icon || 'document'" size="14" />
                  <span>{{ item.label }}</span>
                  <el-button
                    size="small"
                    link
                    @click="removeFavorite(item.id)"
                  >
                    取消收藏
                  </el-button>
                </div>
                <el-empty v-if="favorites.length === 0" description="暂无收藏" :image-size="60" />
              </div>
              <el-space wrap style="margin-top: 12px">
                <el-button @click="addFavoriteData">
                  收藏: 数据管理
                </el-button>
                <el-button @click="addFavoriteDiagram">
                  收藏: 架构图
                </el-button>
                <el-button @click="addFavoriteReport">
                  收藏: 报表分析
                </el-button>
              </el-space>
            </div>
          </el-card>
        </el-col>

        <el-col :span="12">
          <el-card class="test-card">
            <template #header>
              <div class="card-header">
                <span>最近访问记录</span>
                <el-button size="small" link @click="clearRecent">
                  清空
                </el-button>
              </div>
            </template>

            <div class="recent-list">
              <el-timeline>
                <el-timeline-item
                  v-for="item in recentItems.slice(0, 8)"
                  :key="item.id"
                  :timestamp="formatTime(item.visitedAt)"
                  placement="top"
                >
                  <el-card size="small">
                    <div class="recent-item">
                      <AppIcon :name="item.icon || 'document'" size="14" />
                      <span>{{ item.label }}</span>
                      <el-tag size="small" type="info">{{ item.type }}</el-tag>
                    </div>
                  </el-card>
                </el-timeline-item>
              </el-timeline>
              <el-empty v-if="recentItems.length === 0" description="暂无访问记录" :image-size="60" />
            </div>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16" style="margin-top: 16px">
        <el-col :span="24">
          <el-card class="test-card">
            <template #header>
              <div class="card-header">
                <span>组件状态监控</span>
              </div>
            </template>

            <el-descriptions :column="4" border>
              <el-descriptions-item label="当前用户">
                {{ currentUser?.name || '未登录' }}
              </el-descriptions-item>
              <el-descriptions-item label="未读通知">
                {{ unreadCount }}
              </el-descriptions-item>
              <el-descriptions-item label="当前 Tab">
                {{ activeTabId }}
              </el-descriptions-item>
              <el-descriptions-item label="Tab 数量">
                {{ tabs.length }}
              </el-descriptions-item>
              <el-descriptions-item label="收藏夹数量">
                {{ favoriteCount }}
              </el-descriptions-item>
              <el-descriptions-item label="最近访问数量">
                {{ recentCount }}
              </el-descriptions-item>
              <el-descriptions-item label="活跃菜单">
                {{ activeMenuItem }}
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16" style="margin-top: 16px">
        <el-col :span="24">
          <el-card class="test-card">
            <template #header>
              <div class="card-header">
                <span>快捷操作</span>
              </div>
            </template>

            <el-space wrap>
              <el-button @click="testOpenTab">
                测试打开 Tab
              </el-button>
              <el-button @click="testCloseTab">
                测试关闭当前 Tab
              </el-button>
              <el-button @click="testSetUser">
                模拟用户登录
              </el-button>
              <el-button @click="testSetNotifications">
                模拟收到通知
              </el-button>
              <el-button @click="testRecordVisit">
                记录一次访问
              </el-button>
              <el-button @click="openAIAssistant">
                打开 AI 助手
              </el-button>
            </el-space>

            <el-divider />

            <el-space wrap>
              <el-button @click="navigateTo('/')">
                首页
              </el-button>
              <el-button @click="navigateTo('/archdata-chart')">
                架构图
              </el-button>
              <el-button @click="navigateTo('/data')">
                数据管理
              </el-button>
              <el-button @click="navigateTo('/product-version')">
                产品版本
              </el-button>
            </el-space>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <el-dialog
      v-model="aiDialogVisible"
      title="AI 智能助手"
      width="600px"
    >
      <div class="ai-dialog-content">
        <el-empty
          description="AI 助手功能开发中..."
          :image-size="100"
        />
        <p class="ai-description">
          集成后，AI 将能够：
        </p>
        <ul class="ai-features">
          <li>理解您在多个 Tab 中的工作上下文</li>
          <li>基于访问历史推荐相关功能</li>
          <li>跨模块智能搜索和建议</li>
          <li>自动化工作流程建议</li>
        </ul>
      </div>
    </el-dialog>

    <el-dialog
      v-model="favoritesDialogVisible"
      title="收藏夹"
      width="500px"
    >
      <div class="favorites-dialog-content">
        <el-empty
          v-if="favorites.length === 0"
          description="暂无收藏，点击顶部星标添加"
          :image-size="80"
        />
        <div v-else class="favorites-grid">
          <div
            v-for="item in favorites"
            :key="item.id"
            class="favorite-grid-item"
          >
            <div class="favorite-info">
              <AppIcon :name="item.icon || 'document'" size="20" />
              <span class="favorite-label">{{ item.label }}</span>
            </div>
            <el-button
              size="small"
              link
              type="danger"
              @click="removeFavorite(item.id)"
            >
              移除
            </el-button>
          </div>
        </div>
      </div>
    </el-dialog>

    <el-dialog
      v-model="recentDialogVisible"
      title="最近访问"
      width="600px"
    >
      <div class="recent-dialog-content">
        <el-empty
          v-if="recentItems.length === 0"
          description="暂无访问记录"
          :image-size="80"
        />
        <el-timeline v-else>
          <el-timeline-item
            v-for="item in recentItems.slice(0, 15)"
            :key="item.id"
            :timestamp="formatTime(item.visitedAt)"
            placement="top"
          >
            <el-card size="small" class="recent-card">
              <div class="recent-item">
                <AppIcon :name="item.icon || 'document'" size="14" />
                <span>{{ item.label }}</span>
                <el-tag size="small" type="info">{{ item.type }}</el-tag>
              </div>
            </el-card>
          </el-timeline-item>
        </el-timeline>
      </div>
    </el-dialog>
  </AppLayout>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
// [DEV-ONLY] NavigationTest 是导航演示页面, 故意用 ElMessage 演示交互反馈
import { ElMessage } from 'element-plus'
import { AppLayout } from '@/components/common'
import { AppIcon } from '@/components/common'
import { useAppStore } from '@/stores/appStore'
import { useTabStore } from '@/stores/tabStore'
import { useNotificationStore } from '@/stores/notificationStore'

const router = useRouter()
const appStore = useAppStore()
const tabStore = useTabStore()
const notificationStore = useNotificationStore()

const currentUser = computed(() => appStore.currentUser)
const unreadCount = computed(() => notificationStore.unreadCount)
const activeTabId = computed(() => tabStore.activeTabId)
const tabs = computed(() => tabStore.tabs)
const favorites = computed(() => appStore.favorites)
const recentItems = computed(() => appStore.recentItems)
const favoriteCount = computed(() => appStore.favoriteCount)
const recentCount = computed(() => appStore.recentCount)

const activeMenuItem = ref('home')

const aiDialogVisible = ref(false)
const favoritesDialogVisible = ref(false)
const recentDialogVisible = ref(false)

const breadcrumbs = ref([
  { label: '首页', to: '/' },
  { label: '导航系统测试' }
])

const searchSuggestions = ref([
  { id: '1', title: '架构数据管理', type: 'page' },
  { id: '2', title: '架构图', type: 'page' },
  { id: '3', title: '产品版本管理', type: 'page' }
])

const recentSearches = ref(['架构图', '数据管理'])

const menuItems = ref([
  { key: 'home', label: '首页', icon: 'Home', to: '/' },
  { key: 'archdata-chart', label: '架构图', icon: 'Document', to: '/archdata-chart' },
  { key: 'data', label: '数据管理', icon: 'DataAnalysis', to: '/data' },
  { key: 'product', label: '产品版本', icon: 'Goods', to: '/product-version' },
  { key: 'system', label: '系统管理', icon: 'Setting', children: [
    { key: 'business-config', label: '业务配置', to: '/business-config' },
    { key: 'user-permission', label: '用户权限', to: '/user-permission' }
  ]}
])

function handleLogoClick() {
  ElMessage.success('Logo clicked')
}

function handleNotificationClick() {
  ElMessage.info('Notification panel clicked')
}

function handleSearch(keyword) {
  ElMessage.success(`Search: ${keyword}`)
  recentSearches.value.unshift(keyword)
  if (recentSearches.value.length > 5) {
    recentSearches.value.pop()
  }
}

function handleSuggestionClick(suggestion) {
  ElMessage.success(`Suggestion clicked: ${suggestion.title}`)
  router.push(suggestion.title.includes('架构图') ? '/archdata-chart' : '/')
}

function handleUserCommand(key) {
  ElMessage.info(`User command: ${key}`)
  if (key === 'logout') {
    appStore.logout()
    ElMessage.success('Logged out')
  }
}

function handleSidebarSelect(key) {
  activeMenuItem.value = key
  ElMessage.info(`Menu selected: ${key}`)
  appStore.addRecentItem({
    label: menuItems.value.find(i => i.key === key)?.label || key,
    path: `/${key}`,
    icon: menuItems.value.find(i => i.key === key)?.icon,
    type: 'page'
  })
}

function handleSidebarCollapse(collapsed) {
  ElMessage.info(`Sidebar ${collapsed ? 'expanded' : 'hidden'}`)
}

function handleTabChange(tabId) {
  ElMessage.info(`Tab changed to: ${tabId}`)
}

function handleTabClose(tabId) {
  ElMessage.info(`Tab closed: ${tabId}`)
}

function handleAIClick() {
  aiDialogVisible.value = true
}

function handleFavoritesClick() {
  favoritesDialogVisible.value = true
}

function handleRecentClick() {
  recentDialogVisible.value = true
}

function openAIAssistant() {
  aiDialogVisible.value = true
}

function testOpenTab() {
  const tabId = `/test-page-${Date.now()}`
  tabStore.openTab({
    id: tabId,
    label: `测试页面 ${Date.now()}`,
    path: tabId
  })
  ElMessage.success('Tab opened')
}

function testCloseTab() {
  if (activeTabId.value) {
    tabStore.closeTab(activeTabId.value)
    ElMessage.success('Tab closed')
  } else {
    ElMessage.warning('No active tab to close')
  }
}

function testSetUser() {
  appStore.setUser({
    id: '1',
    name: '测试用户',
    email: 'test@example.com',
    role: '管理员'
  })
  ElMessage.success('User set')
}

function testSetNotifications() {
  notificationStore.setNotifications([
    { id: '1', title: '新消息 1', read: false },
    { id: '2', title: '新消息 2', read: false },
    { id: '3', title: '已读消息', read: true }
  ])
  ElMessage.success('Notifications set')
}

function testRecordVisit() {
  appStore.addRecentItem({
    label: '手动访问记录',
    path: '/manual-visit',
    icon: 'Edit',
    type: 'page'
  })
  ElMessage.success('Visit recorded')
}

function addFavoriteData() {
  appStore.addFavorite({
    id: '/data',
    label: '数据管理',
    path: '/data',
    icon: 'DataAnalysis',
    type: 'page'
  })
  ElMessage.success('Added to favorites')
}

function addFavoriteDiagram() {
  appStore.addFavorite({
    id: '/archdata-chart',
    label: '架构图',
    path: '/archdata-chart',
    icon: 'Document',
    type: 'page'
  })
  ElMessage.success('Added to favorites')
}

function addFavoriteReport() {
  appStore.addFavorite({
    id: '/report',
    label: '报表分析',
    path: '/report',
    icon: 'DataLine',
    type: 'page'
  })
  ElMessage.success('Added to favorites')
}

function removeFavorite(id) {
  appStore.removeFavorite(id)
  ElMessage.info('Removed from favorites')
}

function clearRecent() {
  appStore.clearRecentItems()
  ElMessage.success('Recent items cleared')
}

function openDataTab() {
  const tabId = '/data'
  if (!tabStore.tabs.find(t => t.id === tabId)) {
    tabStore.openTab({
      id: tabId,
      label: '数据管理',
      path: tabId,
      icon: 'DataAnalysis'
    })
  } else {
    tabStore.switchTab(tabId)
  }
  ElMessage.info('Opened: Data Management Tab')
}

function openDiagramTab() {
  const tabId = '/archdata-chart'
  if (!tabStore.tabs.find(t => t.id === tabId)) {
    tabStore.openTab({
      id: tabId,
      label: '架构图',
      path: tabId,
      icon: 'Document'
    })
  } else {
    tabStore.switchTab(tabId)
  }
  ElMessage.info('Opened: Architecture Diagram Tab')
}

function openReportTab() {
  const tabId = '/report'
  if (!tabStore.tabs.find(t => t.id === tabId)) {
    tabStore.openTab({
      id: tabId,
      label: '报表分析',
      path: tabId,
      icon: 'DataLine'
    })
  } else {
    tabStore.switchTab(tabId)
  }
  ElMessage.info('Opened: Report Tab')
}

function navigateTo(path) {
  router.push(path)
  appStore.addRecentItem({
    label: getPageName(path),
    path: path,
    icon: getPageIcon(path),
    type: 'page'
  })
}

function getPageName(path) {
  const names = {
    '/': '首页',
    '/archdata-chart': '架构图',
    '/data': '数据管理',
    '/product-version': '产品版本'
  }
  return names[path] || path
}

function getPageIcon(path) {
  const icons = {
    '/': 'Home',
    '/archdata-chart': 'Document',
    '/data': 'DataAnalysis',
    '/product-version': 'Goods'
  }
  return icons[path] || 'Document'
}

function formatTime(isoString) {
  if (!isoString) return ''
  const date = new Date(isoString)
  const now = new Date()
  const diff = now.getTime() - date.getTime()

  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return date.toLocaleDateString('zh-CN')
}
</script>

<style scoped>
.navigation-test {
  padding: var(--spacing-md);
}

.test-card {
  height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.feature-section h4 {
  margin: var(--spacing-md) 0 var(--spacing-sm);
  color: var(--el-text-color-primary);
}

.description {
  color: var(--el-text-color-secondary);
  font-size: var(--el-font-size-small);
  margin-bottom: var(--spacing-md);
}

.favorites-list {
  max-height: 200px;
  overflow-y: auto;
}

.favorite-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.favorite-item:last-child {
  border-bottom: none;
}

.favorite-item span {
  flex: 1;
}

.recent-list {
  max-height: 400px;
  overflow-y: auto;
}

.recent-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.recent-item span {
  flex: 1;
}

.ai-dialog-content,
.favorites-dialog-content,
.recent-dialog-content {
  min-height: 200px;
}

.ai-description {
  text-align: center;
  color: var(--el-text-color-secondary);
  margin: var(--spacing-lg) 0;
}

.ai-features {
  list-style: none;
  padding: 0;
  margin: 0;
}

.ai-features li {
  padding: var(--spacing-sm) 0;
  color: var(--el-text-color-regular);
}

.ai-features li::before {
  content: '[DECORATIVE] ';
  color: var(--yonyou-orange-600);
  font-weight: bold;
}

.favorite-list-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) 0;
}

.favorites-grid {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.favorite-grid-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md);
  background: var(--el-fill-color-light);
  border-radius: var(--el-border-radius-base);
  transition: all 0.2s;
}

.favorite-grid-item:hover {
  background: var(--el-fill-color);
}

.favorite-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.favorite-info .favorite-label {
  flex: 1;
}

.recent-card {
  cursor: pointer;
  transition: all 0.2s;
}

.recent-card:hover {
  background: var(--el-fill-color-light);
}

.el-space {
  margin-top: var(--spacing-md);
}
</style>
