<template>
  <div class="arch-workspace" :class="{ 'desktop-mode': isDesktop }">
    <!-- Desktop 模式标题栏 -->
    <div v-if="isDesktop" class="desktop-titlebar">
      <div class="titlebar-drag-area">
        <span class="titlebar-icon">🏛️</span>
        <span class="titlebar-text">ArchWorkspace</span>
      </div>
      <div class="titlebar-controls">
        <button class="titlebar-btn minimize" @click="minimizeWindow" title="最小化">
          <span>−</span>
        </button>
        <button class="titlebar-btn maximize" @click="maximizeWindow" title="最大化">
          <span>□</span>
        </button>
        <button class="titlebar-btn close" @click="closeWindow" title="关闭">
          <span>×</span>
        </button>
      </div>
    </div>

    <!-- 顶部导航栏 -->
    <header class="workspace-header">
      <div class="logo">
        <span class="logo-icon">🏛️</span>
        <h1>ArchWorkspace</h1>
        <span v-if="isDesktop" class="desktop-badge">Desktop</span>
      </div>
      <div class="header-actions">
        <button class="action-btn" title="设置" @click="openApp('config')">
          <span>⚙️</span>
        </button>
        <button class="action-btn" title="帮助">
          <span>❓</span>
        </button>
      </div>
    </header>

    <!-- 主内容区 -->
    <main class="workspace-main">
      <div class="welcome-section">
        <h2 class="welcome-title">欢迎使用 ArchWorkspace</h2>
        <p class="welcome-desc">架构师工作空间，提供专业的架构设计工具</p>
      </div>

      <!-- 应用卡片网格 -->
      <div class="apps-grid">
        <!-- AA图应用 -->
        <div class="app-card" @click="openApp('aadiagram')">
          <div class="app-icon">
            <span>📊</span>
          </div>
          <div class="app-info">
            <h3 class="app-name">AA图</h3>
            <p class="app-desc">业务对象关系图生成工具</p>
            <div class="app-tags">
              <span class="tag">架构</span>
              <span class="tag">可视化</span>
            </div>
          </div>
          <div class="app-arrow">
            <span>→</span>
          </div>
        </div>

        <!-- 配置应用 -->
        <div class="app-card" @click="openApp('config')">
          <div class="app-icon">
            <span>⚙️</span>
          </div>
          <div class="app-info">
            <h3 class="app-name">配置</h3>
            <p class="app-desc">系统配置与参数设置</p>
            <div class="app-tags">
              <span class="tag">设置</span>
              <span class="tag">管理</span>
            </div>
          </div>
          <div class="app-arrow">
            <span>→</span>
          </div>
        </div>
      </div>

      <!-- 最近使用 -->
      <div class="recent-section" v-if="recentItems.length > 0">
        <h3 class="section-title">最近使用</h3>
        <div class="recent-list">
          <div 
            v-for="item in recentItems" 
            :key="item.id"
            class="recent-item"
            @click="openRecent(item)"
          >
            <span class="recent-icon">{{ item.icon }}</span>
            <span class="recent-name">{{ item.name }}</span>
            <span class="recent-time">{{ item.time }}</span>
          </div>
        </div>
      </div>
    </main>

    <!-- 底部版权 -->
    <footer class="workspace-footer">
      <p>© 2024 ArchWorkspace. All rights reserved.</p>
    </footer>
  </div>
</template>

<script>
export default {
  name: 'ArchWorkspace',
  emits: ['open-app'],
  data() {
    return {
      recentItems: [],
      isDesktop: false,
      appVersion: ''
    }
  },
  mounted() {
    this.checkDesktopMode()
    this.loadRecentItems()
  },
  methods: {
    checkDesktopMode() {
      // 检测是否在 Electron 桌面环境中运行
      this.isDesktop = window.electronAPI?.isElectron || window.desktopMode || false

      // 如果处于桌面模式，获取应用版本
      if (this.isDesktop && window.electronAPI) {
        window.electronAPI.getAppVersion().then(version => {
          this.appVersion = version
        })
      }
    },
    loadRecentItems() {
      // 从 localStorage 加载最近使用的项目
      const saved = localStorage.getItem('archWorkspaceRecent')
      if (saved) {
        try {
          this.recentItems = JSON.parse(saved)
        } catch (e) {
          console.error('加载最近使用记录失败:', e)
        }
      }
    },
    openApp(appName) {
      this.$emit('open-app', appName)
      this.addToRecent(appName)
    },
    openRecent(item) {
      this.$emit('open-app', item.app)
    },
    addToRecent(appName) {
      const appInfo = {
        aadiagram: { name: 'AA图', icon: '📊' },
        config: { name: '配置', icon: '⚙️' }
      }

      const info = appInfo[appName]
      if (!info) return

      // 移除已存在的相同项目
      this.recentItems = this.recentItems.filter(item => item.app !== appName)

      // 添加到开头
      this.recentItems.unshift({
        id: Date.now(),
        app: appName,
        name: info.name,
        icon: info.icon,
        time: new Date().toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
      })

      // 只保留最近 5 个
      this.recentItems = this.recentItems.slice(0, 5)

      // 保存到 localStorage
      localStorage.setItem('archWorkspaceRecent', JSON.stringify(this.recentItems))
    },

    // Desktop 模式窗口控制
    minimizeWindow() {
      if (window.electronAPI?.minimizeWindow) {
        window.electronAPI.minimizeWindow()
      }
    },
    maximizeWindow() {
      if (window.electronAPI?.maximizeWindow) {
        window.electronAPI.maximizeWindow()
      }
    },
    closeWindow() {
      if (window.electronAPI?.closeWindow) {
        window.electronAPI.closeWindow()
      }
    }
  }
}
</script>

<style scoped>
.arch-workspace {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

/* Desktop 模式标题栏 */
.desktop-titlebar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 32px;
  background: #2d2d2d;
  -webkit-app-region: drag;
  user-select: none;
}

.titlebar-drag-area {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  flex: 1;
  -webkit-app-region: drag;
}

.titlebar-icon {
  font-size: 14px;
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
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.titlebar-btn:hover {
  background: rgba(255, 255, 255, 0.1);
}

.titlebar-btn.close:hover {
  background: #e81123;
}

.desktop-badge {
  font-size: 11px;
  padding: 2px 8px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  border-radius: 10px;
  margin-left: 8px;
}

/* Desktop 模式调整 */
.desktop-mode .workspace-header {
  padding-top: 12px;
  padding-bottom: 12px;
}

/* 顶部导航栏 */
.workspace-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 32px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  box-shadow: 0 2px 20px rgba(0, 0, 0, 0.1);
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-icon {
  font-size: 32px;
}

.logo h1 {
  font-size: 24px;
  font-weight: 700;
  color: #333;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.action-btn {
  width: 40px;
  height: 40px;
  border: none;
  background: #f5f5f5;
  border-radius: 8px;
  cursor: pointer;
  font-size: 18px;
  transition: all 0.2s;
}

.action-btn:hover {
  background: #e0e0e0;
  transform: translateY(-2px);
}

/* 主内容区 */
.workspace-main {
  flex: 1;
  padding: 40px 32px;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
}

.welcome-section {
  text-align: center;
  margin-bottom: 48px;
  color: white;
}

.welcome-title {
  font-size: 36px;
  font-weight: 700;
  margin-bottom: 12px;
  text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.2);
}

.welcome-desc {
  font-size: 18px;
  opacity: 0.9;
}

/* 应用卡片网格 */
.apps-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 24px;
  margin-bottom: 48px;
}

.app-card {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 24px;
  background: white;
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
  cursor: pointer;
  transition: all 0.3s ease;
}

.app-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.15);
}

.app-icon {
  width: 64px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  font-size: 32px;
  flex-shrink: 0;
}

.app-info {
  flex: 1;
}

.app-name {
  font-size: 20px;
  font-weight: 600;
  color: #333;
  margin: 0 0 8px 0;
}

.app-desc {
  font-size: 14px;
  color: #666;
  margin: 0 0 12px 0;
}

.app-tags {
  display: flex;
  gap: 8px;
}

.tag {
  padding: 4px 10px;
  background: #f0f0f0;
  border-radius: 4px;
  font-size: 12px;
  color: #666;
}

.app-arrow {
  font-size: 24px;
  color: #999;
  transition: all 0.2s;
}

.app-card:hover .app-arrow {
  color: #667eea;
  transform: translateX(4px);
}

/* 最近使用 */
.recent-section {
  background: rgba(255, 255, 255, 0.95);
  border-radius: 16px;
  padding: 24px;
  backdrop-filter: blur(10px);
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  margin: 0 0 16px 0;
}

.recent-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.recent-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #f9f9f9;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.recent-item:hover {
  background: #f0f0f0;
}

.recent-icon {
  font-size: 20px;
}

.recent-name {
  flex: 1;
  font-size: 14px;
  color: #333;
}

.recent-time {
  font-size: 12px;
  color: #999;
}

/* 底部版权 */
.workspace-footer {
  padding: 20px;
  text-align: center;
  color: rgba(255, 255, 255, 0.7);
  font-size: 14px;
}

.workspace-footer p {
  margin: 0;
}

/* ==================== 响应式设计 ==================== */

/* 平板设备 (768px - 1024px) */
@media screen and (max-width: 1024px) {
  .workspace-main {
    padding: 32px 24px;
  }

  .welcome-title {
    font-size: 28px;
  }

  .welcome-desc {
    font-size: 16px;
  }

  .apps-grid {
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 20px;
  }
}

/* 手机设备 (< 768px) */
@media screen and (max-width: 768px) {
  /* Desktop 标题栏调整 */
  .desktop-titlebar {
    height: 40px;
  }

  .titlebar-btn {
    width: 50px;
    height: 40px;
  }

  /* 顶部导航栏 */
  .workspace-header {
    padding: 12px 16px;
  }

  .logo-icon {
    font-size: 24px;
  }

  .logo h1 {
    font-size: 18px;
  }

  .desktop-badge {
    font-size: 10px;
    padding: 2px 6px;
  }

  .header-actions {
    gap: 8px;
  }

  .action-btn {
    width: 36px;
    height: 36px;
    font-size: 16px;
  }

  /* 主内容区 */
  .workspace-main {
    padding: 24px 16px;
  }

  .welcome-section {
    margin-bottom: 32px;
  }

  .welcome-title {
    font-size: 24px;
    margin-bottom: 8px;
  }

  .welcome-desc {
    font-size: 14px;
  }

  /* 应用卡片 - 垂直布局 */
  .apps-grid {
    grid-template-columns: 1fr;
    gap: 16px;
    margin-bottom: 32px;
  }

  .app-card {
    padding: 16px;
    gap: 16px;
  }

  .app-icon {
    width: 56px;
    height: 56px;
    font-size: 28px;
    border-radius: 12px;
  }

  .app-name {
    font-size: 18px;
    margin-bottom: 4px;
  }

  .app-desc {
    font-size: 13px;
    margin-bottom: 8px;
  }

  .app-tags {
    flex-wrap: wrap;
  }

  .tag {
    font-size: 11px;
    padding: 3px 8px;
  }

  .app-arrow {
    font-size: 20px;
  }

  /* 最近使用 */
  .recent-section {
    padding: 16px;
    border-radius: 12px;
  }

  .section-title {
    font-size: 16px;
    margin-bottom: 12px;
  }

  .recent-item {
    padding: 10px 12px;
  }

  .recent-icon {
    font-size: 18px;
  }

  .recent-name {
    font-size: 13px;
  }

  .recent-time {
    font-size: 11px;
  }

  /* 底部版权 */
  .workspace-footer {
    padding: 16px;
    font-size: 12px;
  }
}

/* 小屏手机 (< 480px) */
@media screen and (max-width: 480px) {
  .workspace-header {
    padding: 10px 12px;
  }

  .logo h1 {
    font-size: 16px;
  }

  .desktop-badge {
    display: none; /* 小屏隐藏 badge */
  }

  .workspace-main {
    padding: 20px 12px;
  }

  .welcome-title {
    font-size: 20px;
  }

  .welcome-desc {
    font-size: 13px;
  }

  .app-card {
    padding: 14px;
  }

  .app-icon {
    width: 48px;
    height: 48px;
    font-size: 24px;
  }

  .app-name {
    font-size: 16px;
  }

  .app-desc {
    font-size: 12px;
  }
}

/* 横屏模式优化 */
@media screen and (max-height: 600px) and (orientation: landscape) {
  .workspace-main {
    padding: 20px 24px;
  }

  .welcome-section {
    margin-bottom: 24px;
  }

  .welcome-title {
    font-size: 22px;
  }

  .apps-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
  }
}

/* 触摸设备优化 */
@media (hover: none) and (pointer: coarse) {
  .app-card:hover {
    transform: none;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
  }

  .app-card:active {
    transform: scale(0.98);
    background: #f8f8f8;
  }

  .action-btn:hover {
    transform: none;
  }

  .recent-item:hover {
    background: #f9f9f9;
  }

  .recent-item:active {
    background: #e8e8e8;
  }
}

/* 深色模式支持 */
@media (prefers-color-scheme: dark) {
  .workspace-header {
    background: rgba(30, 30, 30, 0.95);
  }

  .logo h1 {
    color: #fff;
  }

  .action-btn {
    background: #3a3a3a;
    color: #fff;
  }

  .action-btn:hover {
    background: #4a4a4a;
  }

  .app-card {
    background: #2a2a2a;
  }

  .app-name {
    color: #fff;
  }

  .app-desc {
    color: #aaa;
  }

  .tag {
    background: #3a3a3a;
    color: #ccc;
  }

  .recent-section {
    background: rgba(30, 30, 30, 0.95);
  }

  .section-title {
    color: #fff;
  }

  .recent-item {
    background: #3a3a3a;
  }

  .recent-item:hover {
    background: #4a4a4a;
  }

  .recent-name {
    color: #fff;
  }
}
</style>