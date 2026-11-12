# Spec: 预存 E2E 失败修复（只改用例/测试辅助，不改产品代码）

## 背景与范围

桌面 `--project=features` 跑 5 个文件（29 测）现状：10 passed / 2 skipped / **17 failed**。

失败清单与根因（均已取证）：

| 文件 | 用例 | 根因 |
|---|---|---|
| audit-log.spec.js | F07-F09 [role/product/version] | 详情页 tab 已从 `el-tabs` 改为 ObjectPageContent 的 `.anchor-tab` 按钮，用例仍找 `.el-tabs__item/.tab-item/text=操作日志` |
| deep-insert.spec.js | C01/C02 | `ArchDataPage.openTab` 仍点 `.el-tabs__item:has-text("业务对象")`；MultiObjectManagementPage 2026-08-21 起改为 `.momp-tab-btn` |
| delete-validation-ui.spec.js | C01 | `searchTerm` 收到的是 `ctx = { pv }`，用例按 `pv.product` 取值 → `pv.product` undefined |
| delete-validation-ui.spec.js | C02 | `dataFinder.userGroupWithMember` 不存在；fixture 只暴露 `userGroup()` |
| delete-validation-ui.spec.js | C03 | product code `DVU_C03_${generateId()}` 含小写/连字符 → 400 `^[A-Z][A-Z0-9_]*$` |
| pagination.spec.js | C01-C05 | 同 deep-insert：`ArchDataPage.openTab` 找已废弃的 el-tabs |
| product-version-crud.spec.js | V03/V05 | `dataFinder.createProductWithVersion` 建版本用 `name: '版本 1.0'`（含空格/中文）→ 400 `^[A-Za-z0-9][A-Za-z0-9_.\-]*$`；且用例把返回对象整体当 product（未解构 `{ product }`） |
| product-version-crud.spec.js | V06/V07 | 未导航时 `page.evaluate(fetch('/api/...'))` 在 about:blank 无法解析相对 URL |

## 决策（只动测试侧）

1. **POM 兼容双结构**：`e2e/page-objects/ArchDataPage.js#openTab` 改为优先 `.momp-tab-btn`（含 `:visible`），保留 `.el-tabs__item` 兜底。
2. **详情页日志 tab**：`e2e/features/audit-log.spec.js#switchToAuditLogTabAndAssertLogs` 的候选选择器加入 `.anchor-tab:has-text("操作日志")`（ObjectPageContent L10-19 的真实结构），保留旧候选。
3. **data-finder 版本命名合规**：`e2e/helpers/data-finder.js#createProductWithVersion` 版本 `name` 由 `'版本 1.0'` → `'V1.0'`（同时符合后端正则，保持 code `V1` 不变）。
4. **delete-validation C01**：`searchTerm: (ctx) => ctx.pv.product.name || ctx.pv.product.code`。
5. **delete-validation C02**：按现有 fixture 能力重写 setupData：
   - `isolation.createTracked('user_group', { code: isolation.generateCode('DVU_UG'), name: ... })`
   - 取一个 user（`GET /api/v2/bo/user?page_size=1`），`POST /api/v2/bo/user_group/{id}/associations/members` body `{ target_id, target_type: 'user' }`
   - 用 `GET /api/v2/bo/user_group/{id}` 校验 `member_count >= 1`
   - `searchTerm: (ctx) => ctx.group.name`
   - 断言通知后，`DELETE .../associations/members?target_id=` 解除关联，保证 isolation 清理能删掉自建 group。
6. **delete-validation C03**：product `code` 改用 `isolation.generateCode('DVU_C03')`；`name`/`testId` 保持原样用于搜索。
7. **product-version V03/V05**：`const { product } = await dataFinder.createProductWithVersion()`。
8. **product-version V06**：改用 `page.request.post('/api/v2/bo/version', { data: { product_id } })`（`page.request` 自动带 baseURL 与 storageState）。
9. **product-version V07**：把 `page.evaluate` 内 4 次相对 fetch 改为 `page.request`（product 创建补 `visibility: 'private'`、`is_active: true`；version 创建保持 name/product_id）。

## 不修改

- 任何 `src/`、`meta/` 产品代码。
- 已有移动端适配设施（responsive.js / GenericListPage 双端 getter）。
- 不 commit。

## 验证

每个文件改完后串行验证（`retries=0`，避免掩盖）：

```
$env:APP_URL='http://localhost:3004'
npx playwright test --project=features --reporter=line --retries=0 e2e/features/<file>
npx playwright test --project=mobile-features --reporter=line --retries=0 e2e/features/<file>
```

通过标准：5 个文件桌面 17 条失败全部转绿（skip 可接受，且 skip 原因必须是前置数据缺失而非选择器错误）；mobile-features 同文件无新增失败。

## 已知风险

- C02 依赖后端“删含成员的用户组”校验确实存在；若不拒绝，用例仍红 → 作为产品缺陷报告，不改后端。
- F07-F09 若详情页无任何日志（minLogCount=1），可能仍红 → 先确认是否真实无日志，再决定是否降为“tab 可见 + 列表渲染”。
