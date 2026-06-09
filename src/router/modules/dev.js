/**
 * [FR-018] 开发工具路由
 *  - 主题预览、导航测试等开发辅助
 *  - 生产环境可通过配置动态禁用
 */
export default [
  {
    path: '/dev/theme-preview',
    name: 'theme-preview',
    component: () => import('@/views/dev/ThemePreview.vue'),
    meta: { title: '主题预览', devOnly: true }
  },
  {
    path: '/dev/navigation-test',
    name: 'navigation-test',
    component: () => import('@/views/dev/NavigationTest.vue'),
    meta: { title: '导航系统测试', devOnly: true }
  }
]
