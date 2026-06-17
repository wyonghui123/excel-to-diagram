<template>
  <div class="arch-workspace" :class="{ 'desktop-mode': isDesktop }">
    <div v-if="isDesktop" class="desktop-titlebar">
      <div class="titlebar-drag-area">
        <AppIcon name="enabled" size="sm" class="titlebar-icon" />
        <span class="titlebar-text">BIP应用架构管理</span>
      </div>
      <div class="titlebar-controls">
        <button class="titlebar-btn minimize" @click="minimizeWindow" title="最小化">
          <AppIcon name="minus" size="sm" />
        </button>
        <button class="titlebar-btn maximize" @click="maximizeWindow" title="最大化">
          <AppIcon name="enabled" size="sm" />
        </button>
        <button class="titlebar-btn close" @click="closeWindow" title="关闭">
          <AppIcon name="close" size="sm" />
        </button>
      </div>
    </div>

    <main class="workspace-main">
      <section class="section-block">
        <div class="section-header">
          <h2 class="section-title">快捷应用</h2>
        </div>
        <div class="apps-tiles">
          <div 
            v-for="menu in quickApps" 
            :key="menu.menu_code" 
            class="app-tile" 
            @click="openApp(menu.menu_code)"
          >
            <div class="tile-icon tile-icon--warm-orange">
              <el-icon :size="28" style="color: var(--yonyou-orange-600, #ea580c);">
                <component :is="menuIconComponent(menu.icon)" />
              </el-icon>
            </div>
            <div class="tile-info">
              <span class="tile-name">{{ menu.menu_name }}</span>
              <span class="tile-desc">{{ menu.description }}</span>
            </div>
          </div>
        </div>
      </section>

      <section class="section-block">
        <FrequentProductsSection
          :items="favoriteVersions"
          :loading="frequentLoading"
          @open-with-version="handleOpenWithVersion"
        />
      </section>

      <section class="section-block">
        <StatsOverview />
      </section>
    </main>

    <footer class="workspace-footer">
      <p>&copy; 2026 BIP应用架构管理</p>
    </footer>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { AppIcon } from './common/AppIcon'
import FrequentProductsSection from './FrequentProductsSection.vue'
import StatsOverview from './StatsOverview.vue'
import { useVersionContext } from '@/composables/useVersionContext'
import { useAuthStore } from '@/stores/authStore'
import { useMenuPermissions } from '@/composables/useMenuPermissions'

defineOptions({ name: 'ArchWorkspaceNew' })
import {
  HomeFilled,
  FolderOpened,
  PictureFilled,
  Box,
  Setting,
  User,
  Tools,
  List,
  Grid,
  Timer,
  Document,
  DataAnalysis,
  Connection,
  Monitor,
  Calendar,
  Cpu,
  Finished
} from '@element-plus/icons-vue'

const iconComponentMap = {
  Home: HomeFilled,
  FolderOpened,
  PictureFilled,
  Box,
  Setting,
  User,
  Tools,
  List,
  Timer,
  'timer': Timer,
  Document,
  'document': Document,
  DataAnalysis,
  'data-analysis': DataAnalysis,
  Connection,
  'connection': Connection,
  Monitor,
  'monitor': Monitor,
  Calendar,
  'calendar': Calendar,
  Cpu,
  'cpu': Cpu,
  Finished,
  'finished': Finished
}

const menuIconComponent = (iconName) => {
  return iconComponentMap[iconName] || Grid
}

const router = useRouter()
const authStore = useAuthStore()

const isDesktop = ref(false)

const { favoriteVersions, frequentLoading, loadFavoriteVersions } = useVersionContext()
const { accessibleMenus, flatMenus, leafMenus, loading: menuLoading, loadMenuPermissions } = useMenuPermissions()

const tileColorClass = (color) => `tile-icon--${color || 'warm-orange'}`

const quickApps = computed(() => leafMenus.value)

const openApp = (menuCode) => {
  const menu = flatMenus.value.find(m => m.menu_code === menuCode)
  if (menu && menu.menu_path) {
    router.push(menu.menu_path)
    // 路由守卫会自动创建 tab，不需要手动调用 openTab
  }
}

const handleOpenWithVersion = ({ productId, versionId }) => {
  router.push({ path: '/system/archdata', query: { productId, versionId } })
}

const minimizeWindow = () => {
  if (window.electronAPI?.minimizeWindow) {
    window.electronAPI.minimizeWindow()
  }
}

const maximizeWindow = () => {
  if (window.electronAPI?.maximizeWindow) {
    window.electronAPI.maximizeWindow()
  }
}

const closeWindow = () => {
  if (window.electronAPI?.closeWindow) {
    window.electronAPI.closeWindow()
  }
}

const handleLogout = async () => {
  await authStore.logout()
}

const checkDesktopMode = () => {
  isDesktop.value = window.electronAPI?.isElectron || window.desktopMode || false
}

onMounted(async () => {
  checkDesktopMode()
  loadFavoriteVersions()
  await loadMenuPermissions()
})
</script>

<style lang="scss" scoped>
@import '../styles/mixins.scss';

.arch-workspace {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-secondary);
}

.desktop-titlebar {
  @include flex-between;
  height: 32px;
  background: #1a1a2e;
  -webkit-app-region: drag;
  user-select: none;
}

.titlebar-drag-area {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: 0 var(--spacing-md);
  flex: 1;
  -webkit-app-region: drag;
}

.titlebar-icon {
  color: var(--color-primary);
}

.titlebar-text {
  font-size: 12px;
  color: #fff;
  font-weight: 500;
}

.titlebar-controls {
  display: flex;
  -webkit-app-region: no-drag;
}

.titlebar-btn {
  width: 46px;
  height: 32px;
  border: none;
  background: transparent;
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background var(--transition-normal);

  &:hover {
    background: rgba(255, 255, 255, 0.1);
  }

  &.close:hover {
    background: #e81123;
  }
}

.workspace-header {
  @include flex-between;
  padding: var(--spacing-md) var(--spacing-xl);
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border);
}

.logo {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);

  h1 {
    font-size: 18px;
    font-weight: 600;
    color: var(--color-text-primary);
    margin: 0;
  }
}

.logo-icon-wrapper {
  width: 32px;
  height: 32px;
  background: var(--color-primary);
  border-radius: var(--radius-md);
  @include flex-center;
}

.logo-icon {
  color: white;
}

.desktop-badge {
  font-size: 10px;
  padding: 2px var(--spacing-sm);
  background: var(--color-primary);
  color: #fff;
  border-radius: var(--radius-sm);
  font-weight: 500;
}

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.action-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-md);
  cursor: pointer;
  @include flex-center;
  color: var(--color-text-secondary);
  transition: all var(--transition-normal);

  &:hover {
    background: var(--color-primary);
    color: white;
  }
}

.workspace-main {
  flex: 1;
  padding: var(--spacing-xl) var(--spacing-xl);
  max-width: 960px;
  margin: 0 auto;
  width: 100%;
}

.section-block {
  margin-bottom: var(--spacing-xl);
}

.section-header {
  margin-bottom: var(--spacing-md);
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
  padding-left: var(--spacing-sm);
  border-left: 3px solid var(--color-primary);
}

.apps-tiles {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-md);
}

.app-tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-lg) var(--spacing-md);
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--transition-normal);
  border: 1px solid var(--color-border);
  text-align: center;

  &:hover {
    border-color: var(--color-primary);
    box-shadow: var(--shadow-md);
    transform: translateY(-2px);
  }
}

.tile-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-lg);
  @include flex-center;

  &--orange {
    background: #fff7ed;
    color: #ea580c;
  }

  &--blue {
    background: #eff6ff;
    color: #2563eb;
  }

  &--purple {
    background: #f5f3ff;
    color: #7c3aed;
  }

  &--teal {
    background: #f0fdfa;
    color: #0d9488;
  }

  &--indigo {
    background: #eef2ff;
    color: #4f46e5;
  }

  &--warm-orange {
    background: var(--yonyou-orange-50, #fff7ed);
    color: var(--yonyou-orange-600, #ea580c);
  }

  &--warm-coral {
    background: #fff1f0;
    color: #e17055;
  }

  &--warm-amber {
    background: #fffbeb;
    color: #f59e0b;
  }

  &--warm-rose {
    background: #fff1f2;
    color: #f43f5e;
  }
}

.tile-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tile-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.tile-desc {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.workspace-footer {
  padding: var(--spacing-lg);
  text-align: center;

  p {
    margin: 0;
    font-size: 12px;
    color: var(--color-text-tertiary);
  }
}

@include respond-to('sm') {
  .workspace-header {
    padding: var(--spacing-md) var(--spacing-lg);
  }

  .workspace-main {
    padding: var(--spacing-lg);
  }

  .apps-tiles {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
