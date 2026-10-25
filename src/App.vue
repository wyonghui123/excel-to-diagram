<template>
  <!-- [FR-004] ElConfigProvider 注入 Element Plus locale，替代 app.use 全量注册 -->
  <el-config-provider :locale="epLocale" size="default">
    <div id="app">
      <div v-if="!authStore.sessionReady" class="session-loading">
        <div class="loading-spinner"></div>
      </div>
      <template v-else>
        <!-- [FIX P3 2026-06-30] URL ?help= 公开帮助中心模式: 隐藏 LoginPage, 全屏展示 PublicHelpDrawer
             这样未登录用户访问 ?help= 不会看到登录页, 也不会被 router 跳走 -->
        <template v-if="hasHelpQuery">
          <PublicHelpDrawer />
        </template>
        <template v-else>
          <LoginPage v-if="authEnabled && !authStore.isLoggedIn" />
          <ChangePasswordDialog
            v-else-if="authEnabled && authStore.isLoggedIn && authStore.mustChangePassword"
            :visible="authStore.mustChangePassword"
            @close="handleChangePasswordClose"
          />
          <AppRootLayout v-else>
            <!-- [FR-007] keep-alive 缓存列表与工作台页面 -->
            <!-- [FR-021] ErrorBoundary 捕获路由页面错误 -->
            <ErrorBoundary>
              <router-view v-slot="{ Component }">
                <keep-alive :max="10" :include="cachedRouteNames" :exclude="excludeRouteNames">
                  <component :is="Component" />
                </keep-alive>
              </router-view>
            </ErrorBoundary>
          </AppRootLayout>
        </template>
      </template>
      <NotificationContainer />
    </div>
  </el-config-provider>
</template>

<script setup>
// [FR-014] Options API → <script setup>
import { inject, ref, onMounted } from 'vue'
import LoginPage from './components/LoginPage.vue'
import ChangePasswordDialog from './components/ChangePasswordDialog.vue'
import NotificationContainer from './components/NotificationContainer.vue'
import AppRootLayout from './components/common/AppRootLayout.vue'
import PublicHelpDrawer from './components/common/PublicHelpDrawer/PublicHelpDrawer.vue'
import ErrorBoundary from './components/common/ErrorBoundary.vue'
import { useAuthStore } from './stores/authStore'
import { useMessage } from './composables/useMessage'

const authStore = useAuthStore()
const message = useMessage()

// [FIX P3 2026-06-30] 是否在公开帮助中心模式
//   sessionReady 之后才能确定（不能创建在 setup 阶段, sessionReady 还是 false）
const hasHelpQuery = ref(false)

onMounted(() => {
  hasHelpQuery.value = new URLSearchParams(window.location.search).has('help')
})

// [FR-004] 接收 main.js 注入的 locale
const epLocale = inject('elementPlusLocale', null)

// 认证开关 (默认启用)
const authEnabled = true

// [FR-007] 缓存路由名白名单 (component name, 不是 route name)
const cachedRouteNames = [
  'ArchWorkspaceNew',  // 工作台
  'MetaListPage',      // 通用元数据列表
  'GenericObjectList', // 通用对象列表
  'ObjectDetail',      // 详情查看 (不含编辑)
  'GenericTabContainer', // 通用 Tab 容器 (v-show 保留状态)
  'SourcingRuleDetailContent', // 供应来源规则试算（切换路由后试算结果与 explain 保留）
  // [孤儿页清理 2026-10-17] 移除 'RelationshipManagement'（原第 75 行，注释写"架构数据管理"）:
  //   该页是 ArchDataManagement 的遗留副本(相同 objectTypes / 相同 slots, 且缺嵌入式图表等
  //   9 项能力), 路由早已切到 /system/archdata, /system/relationships 是纯 redirect,
  //   全库无任何引用 —— 成因是 GenericTabContainer 的硬编码映射表漏登记。
  //   注: 本条注释原先声称缓存"架构数据管理", 但承载该页的 ArchDataManagement 并不在白名单里,
  //   即 /system/archdata 实际未被 keep-alive 缓存。此为既存状态, 此次不擅自补入
  //   (ArchDataManagement 内含 Mermaid 命令式图表, 缓存有状态残留与内存开销风险, 需单独评估)。
  // 主数据 hub 页（物料/区划/位置/计量单位/日历/业务伙伴/组织）统一由 MultiObjectHubPage 渲染。
  // 该组件被多页共用，keep-alive 按组件名缓存只会命中同一个实例 ⇒ 跨页串状态，故不纳入白名单。
  // 状态保留不依赖 keep-alive：MOMP 在 onBeforeRouteLeave 用 hub.state_key 写 sessionStorage 快照，
  // 返回时在 onMounted 恢复 scopeIds（树 watch 回写勾选）与 activeTab。7 个 hub 页各有独立
  // state_key，互不覆盖；实测 SPA 往返后勾选与右表过滤均保持。
  // 边界：整页刷新（F5 / 新标签）不保留，因离开时未经过路由守卫写快照。
]

// [FR-007] 明确排除的组件名
const excludeRouteNames = [
  'LoginPage',
  'ChangePasswordDialog',
  'ObjectCreate',  // 创建页面 (表单重置)
]

function handleChangePasswordClose() {
  if (authStore.mustChangePassword) {
    message.warning('请先修改密码')
  }
}
</script>

<style lang="scss">
/* 样式已在 main.js 中统一导入 */

/* [FR-020] 移除全局 * 选择器,引入 modern-normalize 标准化重置 */
@import 'modern-normalize/modern-normalize.css';

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

#app {
  /* [FIX 2026-10-12 移动端] 100dvh 表示"地址栏展开时"的真实视口高度，
     避免手机浏览器地址栏收放时布局跳动；100vh 作为老浏览器回退。 */
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
}

.session-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  height: 100dvh;
  background: var(--color-bg-secondary);
}

.session-loading .loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
