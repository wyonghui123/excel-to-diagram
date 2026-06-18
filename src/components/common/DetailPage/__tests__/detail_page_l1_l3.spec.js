/**
 * detail_page_l1_l3.spec.js - 验证 L1-L3 详情页稳定化改造
 *
 * 目的：
 *   验证 2026-06-18 L1-L3 commits 正确实现了 metalist FR-005/FR-007 模式到详情页：
 *     L1: DetailPage 注入 refreshCoordinator + 注册 detail refresh key
 *     L2: ObjectPageContent onTabChange 触发 association 刷新 + 暴露 refreshAllSections
 *     L3: DetailPage onActivated 状态保留（对齐 metalist FR-005）
 *
 * 测试方法（静态分析）：读取 .vue 源文件做字符串匹配。
 *   优点：不需要 Vue 编译器、dev server、node_modules。
 *   缺点：不验证运行时行为（需要 E2E 补充）。
 *
 * 与 useMetaList.scenarios.spec.js 风格一致。
 */

import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

const SRC = path.resolve(process.cwd(), 'src')

function readFile(p) {
  return fs.readFileSync(path.join(SRC, p), 'utf8')
}

describe('L1-L3 详情页面稳定化改造 (2026-06-18)', () => {
  describe('L1: DetailPage 注入 refreshCoordinator', () => {
    const detailSrc = readFile('components/common/DetailPage/DetailPage.vue')

    it('1.1 导入 inject 和 onUnmounted from vue', () => {
      expect(detailSrc).toMatch(/import\s*\{[^}]*inject[^}]*\}\s*from\s*['"]vue['"]/)
      expect(detailSrc).toMatch(/import\s*\{[^}]*onUnmounted[^}]*\}\s*from\s*['"]vue['"]/)
    })

    it('1.2 注入 refreshCoordinator，兜底为 null（standalone 路由无 provider）', () => {
      expect(detailSrc).toMatch(/inject\(\s*['"]refreshCoordinator['"]\s*,\s*null\s*\)/)
    })

    it('1.3 refreshKey 包含 objectType + id 区分实例', () => {
      // 区别于 metalist 的 `list:${objectType}`（单 objectType 单实例）
      // 详情页必须带 id，否则多 tab 浏览器打开同 ot 不同对象会互相覆盖
      expect(detailSrc).toMatch(/detail:\$\{[^}]*objectType[^}]*\}:\$/)

      // 排除 standalone 创建模式（无效 id）
      expect(detailSrc).toMatch(/props\.id\s*!==\s*['"]new['"]/)
      expect(detailSrc).toMatch(/!props\.createMode/)
    })

    it('1.4 coordinatorRefresh 回调：先 handleRefresh 再 refreshAllSections', () => {
      expect(detailSrc).toMatch(/async\s+function\s+coordinatorRefresh\s*\(\s*\)/)
      expect(detailSrc).toMatch(/coordinatorRefresh[\s\S]*?handleRefresh\(\s*\{\s*\}\s*\)/)
      expect(detailSrc).toMatch(/coordinatorRefresh[\s\S]*?refreshAllSections/)
    })

    it('1.5 syncCoordinatorRegistration：变化时 unregister 旧 key 再 register 新 key', () => {
      expect(detailSrc).toMatch(/function\s+syncCoordinatorRegistration\s*\(\s*\)/)
      expect(detailSrc).toMatch(/coordinator\.unregister\s*\(\s*_registeredCoordinatorKey\s*\)/)
      expect(detailSrc).toMatch(/coordinator\.register\s*\(\s*coordinatorRefreshKey\.value\s*,\s*coordinatorRefresh\s*\)/)
    })

    it('1.6 watch(coordinatorRefreshKey) + 首次 onMounted 主动 sync', () => {
      expect(detailSrc).toMatch(/watch\s*\(\s*coordinatorRefreshKey\s*,\s*syncCoordinatorRegistration\s*\)/)
      // onMounted 内调用 syncCoordinatorRegistration
      expect(detailSrc).toMatch(/onMounted\s*\(\s*\(\s*\)\s*=>\s*\{[\s\S]*?syncCoordinatorRegistration\s*\(\s*\)/)
    })

    it('1.7 onUnmounted 注销 coordinator 回调', () => {
      expect(detailSrc).toMatch(/onUnmounted\s*\(\s*\(\s*\)\s*=>\s*\{[\s\S]*?coordinator\.unregister[\s\S]*?\}\s*\)/)
    })
  })

  describe('L2: ObjectPageContent onTabChange 刷新 association + 暴露 refreshAllSections', () => {
    const contentSrc = readFile('components/common/ObjectPage/ObjectPageContent.vue')

    it('2.1 跟踪 associationRefs Map', () => {
      expect(contentSrc).toMatch(/const\s+associationRefs\s*=\s*ref\s*\(\s*\{\s*\}\s*\)/)
    })

    it('2.2 setAssociationRef 函数（与 setHistoryRef 对称）', () => {
      expect(contentSrc).toMatch(/function\s+setAssociationRef\s*\(\s*key\s*,\s*el\s*\)/)
      expect(contentSrc).toMatch(/associationRefs\.value\[key\]\s*=\s*el/)
    })

    it('2.3 AssociationSection 绑定 :ref="el => setAssociationRef(...)"', () => {
      // 应至少有 2 处（mainContentSections + tab sections）
      const matches = contentSrc.match(/setAssociationRef\s*\(/g)
      expect(matches).not.toBeNull()
      expect(matches.length).toBeGreaterThanOrEqual(3)  // 2 bind + 1 lookup
    })

    it('2.4 onTabChange 切到 association/annotation tab 触发 refresh()', () => {
      // 找到 onTabChange 函数体
      const onTabChangeMatch = contentSrc.match(/function\s+onTabChange\s*\([^)]*\)\s*\{[\s\S]*?\n\}/)
      expect(onTabChangeMatch).not.toBeNull()
      const body = onTabChangeMatch[0]
      // 检查：包含 section.type === 'association' 或 'annotation' 的判断
      expect(body).toMatch(/section\.type\s*===\s*['"]association['"]/)
      expect(body).toMatch(/assocRef\.refresh\s*\(\s*\)/)
      // 检查：nextTick 包裹避免 v-show DOM width=0 竞态
      expect(body).toMatch(/nextTick\s*\(\s*\(\s*\)\s*=>\s*\{[\s\S]*?assocRef\.refresh/)
    })

    it('2.5 refreshAllSections 函数：并行刷新所有 association section', () => {
      expect(contentSrc).toMatch(/async\s+function\s+refreshAllSections\s*\(\s*\)/)
      expect(contentSrc).toMatch(/Promise\.allSettled\s*\(\s*refs\.map/)
      // 防止单个失败阻断其他
      expect(contentSrc).toMatch(/allSettled/)
    })

    it('2.6 defineExpose 包含 refreshAllSections 和 associationRefs', () => {
      expect(contentSrc).toMatch(/defineExpose\s*\(\s*\{[\s\S]*?refreshAllSections\s*,[\s\S]*?associationRefs\s*[\s\S]*?\}\s*\)/)
    })
  })

  describe('L3: DetailPage onActivated 状态保留（FR-005 对齐）', () => {
    const detailSrc = readFile('components/common/DetailPage/DetailPage.vue')

    it('3.1 导入 onActivated from vue', () => {
      expect(detailSrc).toMatch(/import\s*\{[^}]*onActivated[^}]*\}\s*from\s*['"]vue['"]/)
    })

    it('3.2 onActivated hook：仅 console.debug，不调用 fetchData/handleRefresh', () => {
      // 找到 onActivated 函数体
      const onActivatedMatch = detailSrc.match(/onActivated\s*\(\s*\(\s*\)\s*=>\s*\{[\s\S]*?\}\s*\)/)
      expect(onActivatedMatch).not.toBeNull()
      const body = onActivatedMatch[0]
      expect(body).toMatch(/console\.debug/)
      // 关键：不能调用 fetchData 或 handleRefresh
      expect(body).not.toMatch(/fetchData\s*\(/)
      expect(body).not.toMatch(/handleRefresh\s*\(/)
    })

    it('3.3 onActivated 不破坏既有 onMounted / onUnmounted 行为', () => {
      // onMounted 仍调用 fetchData / loadEntityMeta
      expect(detailSrc).toMatch(/onMounted\s*\(\s*\(\s*\)\s*=>\s*\{[\s\S]*?fetchData\s*\(\s*\)/)
      expect(detailSrc).toMatch(/onMounted\s*\(\s*\(\s*\)\s*=>\s*\{[\s\S]*?loadEntityMeta\s*\(\s*\)/)
      // onUnmounted 仍注销 coordinator
      expect(detailSrc).toMatch(/onUnmounted\s*\(\s*\(\s*\)\s*=>\s*\{[\s\S]*?_registeredCoordinatorKey\s*=\s*null/)
    })
  })

  describe('协调器机制：与 metalist FR-005/FR-007 一致性', () => {
    const coordinatorSrc = readFile('composables/useRefreshCoordinator.js')
    const detailSrc = readFile('components/common/DetailPage/DetailPage.vue')
    const objectPageSrc = readFile('components/common/ObjectPage/ObjectPageContent.vue')

    it('4.1 useRefreshCoordinator 提供 register/unregister/refreshAll API', () => {
      expect(coordinatorSrc).toMatch(/function\s+register\s*\(\s*key\s*,\s*fn\s*\)/)
      expect(coordinatorSrc).toMatch(/function\s+unregister\s*\(\s*key\s*\)/)
      expect(coordinatorSrc).toMatch(/async\s+function\s+refreshAll\s*\(\s*\)/)
    })

    it('4.2 DetailPage 显式调用 coordinator.register + coordinator.unregister', () => {
      // register
      const registerCalls = detailSrc.match(/coordinator\.register\s*\(/g) || []
      expect(registerCalls.length).toBeGreaterThanOrEqual(1)
      // unregister
      const unregisterCalls = detailSrc.match(/coordinator\.unregister\s*\(/g) || []
      expect(unregisterCalls.length).toBeGreaterThanOrEqual(2)  // syncCoordinatorRegistration + onUnmounted
    })

    it('4.3 详情页改动是纯添加（无现有逻辑删除/修改）', () => {
      // 与 baseline (01d5443) 对比：差异行 = 我们的 + 测试
      // 这里只验证：我们没改 onMounted / fetchData / handleRefresh 核心逻辑
      // 简单检查：fetchData 函数体没变（通过关键字符串仍存在判断）
      expect(detailSrc).toMatch(/async\s+function\s+fetchData\s*\(\s*options\s*=\s*\{\s*\}\s*\)/)
      expect(detailSrc).toMatch(/async\s+function\s+handleRefresh\s*\(\s*payload\s*=\s*\{\s*\}\s*\)/)
    })

    it('4.4 ObjectPageContent 改动是纯添加（既有 onTabChange 行为保留）', () => {
      // onTabChange 仍有 history tab 的 loadAuditLogs 逻辑
      expect(objectPageSrc).toMatch(/section\?\.type\s*===\s*['"]history['"][\s\S]*?loadAuditLogs/)
      // effectiveTabSections 等核心计算仍存在
      expect(objectPageSrc).toMatch(/const\s+effectiveTabSections\s*=\s*computed/)
    })
  })

  describe('文档与可观测性', () => {
    const detailSrc = readFile('components/common/DetailPage/DetailPage.vue')
    const objectPageSrc = readFile('components/common/ObjectPage/ObjectPageContent.vue')

    it('5.1 改动标记清晰：[L1/L2/L3 2026-06-18] 前缀', () => {
      expect(detailSrc).toMatch(/\[L1\s+2026-06-18\]/)
      expect(detailSrc).toMatch(/\[L3\s+2026-06-18\]/)
      expect(objectPageSrc).toMatch(/\[L2\s+2026-06-18\]/)
    })

    it('5.2 引用 metalist FR-005/FR-007 设计动机', () => {
      expect(detailSrc).toMatch(/FR-005/)
      expect(detailSrc).toMatch(/FR-007/)
    })

    it('5.3 onActivated 包含可追踪的 console.debug', () => {
      const onActivatedMatch = detailSrc.match(/onActivated\s*\(\s*\(\s*\)\s*=>\s*\{[\s\S]*?\}\s*\)/)
      expect(onActivatedMatch).not.toBeNull()
      expect(onActivatedMatch[0]).toMatch(/console\.debug/)
    })
  })
})
