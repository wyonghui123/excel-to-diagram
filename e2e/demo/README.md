# e2e/demo/ 已删除 (Phase 6 融合)

> **本目录已于 2026-06-13 删除 (3 个 demo 文件)**
> 详见: [E2E_MERGE_ROBUSTNESS_REPORT.md §2.2 集群 8](../../../E2E_MERGE_ROBUSTNESS_REPORT.md)

## 为何删除

demo/* 下的 3 个文件 (inspect-menu, pom-migration-demo, simplified-test-demo) 是**临时教学/demo 性质**, 没有持续运行的业务价值:
- 0 业务覆盖
- 包含 console.log 输出的教学占位符
- 文件名带 "demo" / "inspect" 表明是一次性探查

## v2 简化方案 (替代 demo)

实际生产 spec 全部采用以下模式:

```javascript
// [OK] v2 风格: 1 行初始化, 全局自动登录, 自动清理
import { test, expect, navigateTo, withStep, dataFinder } from '../helpers/auto-fixtures.js'
import { ArchDataPage } from '../page-objects/ArchDataPage.js'

test('业务场景', async ({ page, dataFinder, isolation }, testInfo) => {
  // 1. 智能导航 (替代 page.goto + waitForTimeout)
  const pv = await dataFinder.productWithVersion()
  await navigateTo(page, `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}`)

  // 2. POM 操作
  const archData = new ArchDataPage(page)
  await archData.goToBOList().clickRowByName('xxx')

  // 3. 自动清理 (afterEach 自动)
  const bo = await isolation.createTracked('business_object', { code: 'E_TEST' })

  // 4. 业务断言
  expect(...).toBe(...)
})
```

## 想了解迁移背景

阅读:
- [e2e/TEST_SIMPLIFICATION_PLAN.md](../TEST_SIMPLIFICATION_PLAN.md)
- [e2e/TEST_SIMPLIFICATION_REPORT.md](../TEST_SIMPLIFICATION_REPORT.md)
- [E2E_MERGE_ROBUSTNESS_REPORT.md](../../../E2E_MERGE_ROBUSTNESS_REPORT.md)

---

_此 README 是 demo 目录 3 个文件删除后留下的信息密度更高的替代品_
