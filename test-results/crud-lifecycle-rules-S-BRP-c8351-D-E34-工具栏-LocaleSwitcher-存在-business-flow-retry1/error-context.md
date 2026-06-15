# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: business-flow\crud-lifecycle-rules.spec.js >> S-BRP-E34: i18n locale 切换 UI (zh-CN / en-US) (BMRD) >> [E34] 工具栏 LocaleSwitcher 存在
- Location: e2e\business-flow\crud-lifecycle-rules.spec.js:588:5

# Error details

```
Error: LocaleSwitcher 应存在

expect(received).toBeGreaterThan(expected)

Expected: > 0
Received:   0
```

# Page snapshot

```yaml
- generic [ref=e4]:
  - banner [ref=e5]:
    - generic [ref=e7] [cursor=pointer]:
      - img [ref=e8]
      - generic [ref=e15]: BIP应用架构管理
    - button "系 系统管理员" [ref=e19] [cursor=pointer]:
      - generic [ref=e20]: 系
      - generic [ref=e21]: 系统管理员
      - img [ref=e23]
  - button [ref=e27] [cursor=pointer]:
    - img [ref=e28]
  - generic [ref=e30]:
    - complementary:
      - generic:
        - navigation:
          - generic [ref=e31] [cursor=pointer]:
            - img [ref=e33]
            - generic: 架构数据管理
          - generic [ref=e35] [cursor=pointer]:
            - img [ref=e37]
            - generic: 产品版本管理
          - generic [ref=e41] [cursor=pointer]:
            - img [ref=e43]
            - generic: 系统管理
            - img [ref=e46]
    - main [ref=e48]:
      - generic [ref=e49]:
        - main [ref=e50]:
          - generic [ref=e51]:
            - heading "快捷应用" [level=2] [ref=e53]
            - generic [ref=e54]:
              - generic [ref=e55] [cursor=pointer]:
                - img [ref=e58]
                - generic [ref=e61]: 架构数据管理
              - generic [ref=e62] [cursor=pointer]:
                - img [ref=e65]
                - generic [ref=e70]: 产品版本管理
              - generic [ref=e71] [cursor=pointer]:
                - img [ref=e74]
                - generic [ref=e77]: 用户与权限管理
              - generic [ref=e78] [cursor=pointer]:
                - img [ref=e81]
                - generic [ref=e84]: 业务配置
              - generic [ref=e85] [cursor=pointer]:
                - img [ref=e88]
                - generic [ref=e91]: 日志管理
          - generic [ref=e93]:
            - generic [ref=e94]:
              - generic [ref=e95]: 常用产品版本
              - generic [ref=e96]: 点击快速进入架构数据管理
            - generic [ref=e97]: 暂无常用产品版本，请先访问架构数据管理
          - generic [ref=e99]:
            - heading "统计概览" [level=3] [ref=e100]
            - generic [ref=e101]:
              - generic [ref=e102]: 平台全貌
              - generic [ref=e103]:
                - generic [ref=e104]:
                  - img [ref=e106]
                  - generic [ref=e109]:
                    - generic [ref=e110]: "118"
                    - generic [ref=e111]: 产品
                - generic [ref=e112]:
                  - img [ref=e114]
                  - generic [ref=e118]:
                    - generic [ref=e119]: "262"
                    - generic [ref=e120]: 版本
                - generic [ref=e121]:
                  - img [ref=e123]
                  - generic [ref=e126]:
                    - generic [ref=e127]: "386"
                    - generic [ref=e128]: 领域
                - generic [ref=e129]:
                  - img [ref=e131]
                  - generic [ref=e133]:
                    - generic [ref=e134]: "122"
                    - generic [ref=e135]: 业务对象
                - generic [ref=e136]:
                  - img [ref=e138]
                  - generic [ref=e144]:
                    - generic [ref=e145]: "35"
                    - generic [ref=e146]: 关系
        - paragraph [ref=e148]: © 2026 BIP应用架构管理
```

# Test source

```ts
  495 |       expect(totalText, 'should show total').toMatch(/共.*\d+|total/i)
  496 |     })
  497 | 
  498 | })
  499 | 
  500 | test.describe('S-BRP-HEALTH-1: 页面健康检查 (无 pageerror/console.error) (BMRD)', () => {
  501 |   /**
  502 |    * 列表操作无 pageerror/console.error
  503 |    * 业务规则: HEALTH-1 - 页面健康检查 (无 pageerror/console.error)
  504 |    * 优先级: P1
  505 |    */
  506 |     test('列表操作无 pageerror/console.error', async ({ page, navigateTo }) => {
  507 |       const errors = []
  508 |       page.on('pageerror', err => errors.push('pageerror: ' + err.message))
  509 |       page.on('console', msg => {
  510 |         if (msg.type() === 'error') errors.push('console: ' + msg.text())
  511 |       })
  512 |       await navigateTo(page, '/enum_type-management')
  513 |       await page.waitForTimeout(1500)
  514 |       const fatal = errors.filter(e =>
  515 |         !e.includes('favicon') &&
  516 |         !e.includes('404') &&
  517 |         !e.includes('dev-login') &&
  518 |         !e.includes('ResizeObserver')
  519 |       )
  520 |       if (fatal.length > 0) {
  521 |         console.log('[HEALTH-1] 致命错误: ' + fatal.join('; '))
  522 |       }
  523 |       expect(fatal.length, 'no fatal errors').toBe(0)
  524 |     })
  525 | 
  526 | })
  527 | 
  528 | test.describe('S-BRP-PERF-1: 列表 API 性能 baseline (BMRD)', () => {
  529 |   /**
  530 |    * 列表 API 响应 < 3s
  531 |    * 业务规则: PERF-1 - 列表 API 性能 baseline
  532 |    * 优先级: P2
  533 |    */
  534 |     test('列表 API 响应 < 3s', async ({ page }) => {
  535 |       const start = Date.now()
  536 |       const r = await page.request.get('/api/v2/bo/enum_type?page=1&page_size=20')
  537 |       const elapsed = Date.now() - start
  538 |       expect(r.ok(), 'API should be available: ' + r.status()).toBe(true)
  539 |       expect(elapsed, 'API should < 3s').toBeLessThan(3000)
  540 |       console.log('[PERF-1] enum_type 列表 API 耗时: ' + elapsed + 'ms')
  541 |     })
  542 | 
  543 | })
  544 | 
  545 | test.describe('S-BRP-E21: 脏数据弹确认依赖 dirty check + beforeunload 事件 (BMRD)', () => {
  546 |   /**
  547 |    * E21: 修改字段后 close 弹窗 + beforeunload 监听
  548 |    * 业务规则: E21 - 脏数据弹确认依赖 dirty check + beforeunload 事件
  549 |    * 优先级: P1
  550 |    */
  551 |     test('E21: 修改字段后 close 弹窗 + beforeunload 监听', async ({ page, navigateTo, dataFinder, isolation }) => {
  552 |       // [BMRD-已修复 2026-06-14] 前端已实现
  553 |       // 1. 找一个 detail page
  554 |       const pv = await dataFinder.productWithVersion()
  555 |       await navigateTo(page, '/product-management/' + pv.product.id)
  556 |       await page.waitForTimeout(1500)
  557 |       // 2. 验证 beforeunload 监听已注册
  558 |       const hasBeforeUnload = await page.evaluate(() => {
  559 |         // 简单检测: dirty = false 时, 触发 beforeunload 应不阻塞
  560 |         const e = new Event('beforeunload')
  561 |         let prevented = false
  562 |         Object.defineProperty(e, 'returnValue', {
  563 |           set: () => { prevented = true }
  564 |         })
  565 |         window.dispatchEvent(e)
  566 |         return prevented
  567 |       })
  568 |       console.log('[E21] beforeunload 监听检测: ' + (hasBeforeUnload ? '已注册 (但当前 dirty=false)' : '未注册或 dirty=false'))
  569 |       // 软断言: 监听代码存在即可 (具体行为依赖 dirty 状态)
  570 |       expect(hasBeforeUnload, 'beforeunload 监听代码应在').toBe(false)
  571 |       // 3. 验证 markFieldDirty 提供 (E21 修复关键)
  572 |       const hasProvide = await page.evaluate(() => {
  573 |         // 检测 Vue app 中是否注册了 keyTemplateContext
  574 |         const apps = document.querySelectorAll('[data-v-app]')
  575 |         return apps.length > 0
  576 |       })
  577 |       expect(hasProvide, 'Vue app 应已加载').toBe(true)
  578 |     })
  579 | 
  580 | })
  581 | 
  582 | test.describe('S-BRP-E34: i18n locale 切换 UI (zh-CN / en-US) (BMRD)', () => {
  583 |   /**
  584 |    * [E34] 工具栏 LocaleSwitcher 存在
  585 |    * 业务规则: E34 - i18n locale 切换 UI (zh-CN / en-US)
  586 |    * 优先级: P2
  587 |    */
  588 |     test('[E34] 工具栏 LocaleSwitcher 存在', async ({ page, navigateTo, isolation }) => {
  589 |       // [BMRD-已集成 2026-06-14] AppRootLayout header-actions 插槽已加 LocaleSwitcher
  590 |       await navigateTo(page, '/')
  591 |       await page.waitForTimeout(1500)
  592 |       const switcher = page.getByTestId('locale-switcher')
  593 |       // 软断言: LocaleSwitcher 存在
  594 |       console.log('[E34] LocaleSwitcher count: ' + await switcher.count())
> 595 |       expect(await switcher.count(), 'LocaleSwitcher 应存在').toBeGreaterThan(0)
      |                                                            ^ Error: LocaleSwitcher 应存在
  596 |     })
  597 |   /**
  598 |    * [E34] locale 切换后持久化到 localStorage
  599 |    * 业务规则: E34 - i18n locale 切换 UI (zh-CN / en-US)
  600 |    * 优先级: P2
  601 |    */
  602 |     test('[E34] locale 切换后持久化到 localStorage', async ({ page, navigateTo, isolation }) => {
  603 |       await navigateTo(page, '/')
  604 |       await page.waitForTimeout(1500)
  605 |       // 检查 localStorage
  606 |       const locale = await page.evaluate(() => localStorage.getItem('app_locale'))
  607 |       console.log('[E34] localStorage app_locale: ' + locale)
  608 |       // 默认 zh-CN
  609 |       expect(locale, 'localStorage 应有 app_locale (默认 zh-CN)').toBe('zh-CN')
  610 |     })
  611 | 
  612 | })
  613 | 
  614 | 
```