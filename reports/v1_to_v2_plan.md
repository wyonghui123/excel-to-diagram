# v1 → v2 Spec 迁移计划

> **生成时间**: 1780833295.106747
> **生成工具**: scripts/v1_to_v2_migrator.py

---

## 一、概览

| 指标 | 数值 |
|------|------|
| **v1 spec 总数** | **42** |
| **总计需修改处** | **1043** |
| 自动安全修改 | 340 |
| 需手动重构 | 703 |

### 复杂度分布

| 复杂度 | 数量 | 占比 | 单个估时 |
|--------|------|------|---------|
| simple | 0 | 0.0% | 5-10 min (auto-fix + 验证) |
| moderate | 6 | 14.3% | 15-30 min (1-2 POM 重构) |
| complex | 3 | 7.1% | 0.5-1 hour (3-5 处重构) |
| very_complex | 33 | 78.6% | 1-2 hours (深度重构) |

**总估时**: ~53h 57min (42 specs)

---

## 二、推荐迁移顺序 (按 ROI)

优先级规则:
- **P0 (本周)**: simple + moderate (易改) - 立即出价值
- **P1 (下周)**: complex (中等难度)
- **P2 (本月)**: very_complex (高难度)

| 优先级 | 数量 | 总估时 |
|--------|------|--------|
| **P0 本周** | 6 | ~2h |
| **P1 下周** | 3 | ~2h |
| **P2 本月** | 33 | ~49h |

---

## 三、Spec 详细清单 (按 unsafe 变化降序)

| # | Spec | 复杂度 | test 数 | 总变化 | safe | unsafe | 行数 | 估时 |
|---|------|--------|--------:|------:|-----:|------:|-----:|------|
| 1 | `role-permission-center.spec.js` | very_complex | 27 | 127 | 61 | 66 | 1019 | 1-2 hours (深度重构) |
| 2 | `import-export.spec.js` | very_complex | 2 | 68 | 4 | 64 | 676 | 1-2 hours (深度重构) |
| 3 | `arch-data-filter-scope.spec.js` | very_complex | 2 | 53 | 8 | 45 | 255 | 1-2 hours (深度重构) |
| 4 | `audit-log-embedded-access.spec.js` | very_complex | 14 | 53 | 11 | 42 | 442 | 1-2 hours (深度重构) |
| 5 | `arch-data-crud.spec.js` | very_complex | 2 | 43 | 6 | 37 | 466 | 1-2 hours (深度重构) |
| 6 | `user-role.spec.js` | very_complex | 3 | 44 | 9 | 35 | 272 | 1-2 hours (深度重构) |
| 7 | `audit-log-grouping-detail.spec.js` | very_complex | 10 | 40 | 6 | 34 | 237 | 1-2 hours (深度重构) |
| 8 | `enum-management.spec.js` | very_complex | 3 | 37 | 9 | 28 | 346 | 1-2 hours (深度重构) |
| 9 | `product-version.spec.js` | very_complex | 3 | 33 | 9 | 24 | 233 | 1-2 hours (深度重构) |
| 10 | `fk-filter.spec.js` | very_complex | 2 | 28 | 6 | 22 | 169 | 1-2 hours (深度重构) |
| 11 | `relation-scope-field.spec.js` | very_complex | 2 | 29 | 8 | 21 | 193 | 1-2 hours (深度重构) |
| 12 | `audit-log-filter.spec.js` | very_complex | 7 | 23 | 4 | 19 | 235 | 1-2 hours (深度重构) |
| 13 | `audit-log-objects-p1.spec.js` | very_complex | 11 | 22 | 4 | 18 | 353 | 1-2 hours (深度重构) |
| 14 | `ValueHelp-5-layer-link.spec.js` | very_complex | 15 | 17 | 1 | 16 | 233 | 1-2 hours (深度重构) |
| 15 | `audit-log.spec.js` | very_complex | 3 | 24 | 9 | 15 | 186 | 1-2 hours (深度重构) |
| 16 | `value-help-filter.spec.js` | very_complex | 3 | 22 | 7 | 15 | 161 | 1-2 hours (深度重构) |
| 17 | `relation-scope-tree.spec.js` | very_complex | 6 | 20 | 5 | 15 | 526 | 1-2 hours (深度重构) |
| 18 | `audit-log-levels.spec.js` | very_complex | 6 | 19 | 4 | 15 | 298 | 1-2 hours (深度重构) |
| 19 | `condition-rule-dialog-spec-v14.spec.js` | very_complex | 9 | 31 | 17 | 14 | 330 | 1-2 hours (深度重构) |
| 20 | `audit-log-objects-p0.spec.js` | very_complex | 5 | 18 | 4 | 14 | 321 | 1-2 hours (深度重构) |
| 21 | `useMetaList-21-keypath.spec.js` | very_complex | 21 | 15 | 1 | 14 | 209 | 1-2 hours (深度重构) |
| 22 | `fk-filter-issue.spec.js` | very_complex | 2 | 20 | 8 | 12 | 133 | 1-2 hours (深度重构) |
| 23 | `user-permission.spec.js` | very_complex | 2 | 20 | 8 | 12 | 63 | 1-2 hours (深度重构) |
| 24 | `diagram.spec.js` | very_complex | 2 | 19 | 7 | 12 | 131 | 1-2 hours (深度重构) |
| 25 | `audit-log-actions.spec.js` | very_complex | 7 | 16 | 4 | 12 | 183 | 1-2 hours (深度重构) |
| 26 | `audit-log-base.spec.js` | very_complex | 5 | 23 | 12 | 11 | 203 | 1-2 hours (深度重构) |
| 27 | `business-object-crud.spec.js` | very_complex | 2 | 18 | 8 | 10 | 59 | 1-2 hours (深度重构) |
| 28 | `product-crud.spec.js` | very_complex | 2 | 18 | 8 | 10 | 79 | 1-2 hours (深度重构) |
| 29 | `value-help-dialog.spec.js` | very_complex | 1 | 15 | 5 | 10 | 98 | 1-2 hours (深度重构) |
| 30 | `workspace.spec.js` | very_complex | 2 | 16 | 9 | 7 | 54 | 1-2 hours (深度重构) |
| 31 | `user-group-filter.spec.js` | very_complex | 2 | 13 | 6 | 7 | 121 | 1-2 hours (深度重构) |
| 32 | `fk-filter-debug.spec.js` | very_complex | 1 | 11 | 5 | 6 | 102 | 1-2 hours (深度重构) |
| 33 | `fk-filter-search.spec.js` | very_complex | 1 | 11 | 5 | 6 | 64 | 1-2 hours (深度重构) |
| 34 | `condition-rule-dialog.spec.js` | complex | 2 | 10 | 6 | 4 | 73 | 0.5-1 hour (3-5 处重构) |
| 35 | `overlap-warning.spec.js` | complex | 1 | 7 | 4 | 3 | 52 | 0.5-1 hour (3-5 处重构) |
| 36 | `user-group-detail.spec.js` | complex | 1 | 6 | 3 | 3 | 77 | 0.5-1 hour (3-5 处重构) |
| 37 | `menu-bo-linker.spec.js` | moderate | 3 | 10 | 8 | 2 | 66 | 15-30 min (1-2 POM 重构) |
| 38 | `permission-explainer.spec.js` | moderate | 3 | 10 | 8 | 2 | 105 | 15-30 min (1-2 POM 重构) |
| 39 | `debug-column-config.spec.js` | moderate | 1 | 6 | 5 | 1 | 60 | 15-30 min (1-2 POM 重构) |
| 40 | `intent-apis.spec.js` | moderate | 4 | 10 | 10 | 0 | 104 | 15-30 min (1-2 POM 重构) |
| 41 | `role-intents.spec.js` | moderate | 4 | 10 | 10 | 0 | 117 | 15-30 min (1-2 POM 重构) |
| 42 | `data-permission-config.spec.js` | moderate | 3 | 8 | 8 | 0 | 84 | 15-30 min (1-2 POM 重构) |

---

## 四、详细问题分布 (按 pattern)

| v1 模式 | 出现次数 | 需手动 | 风险 |
|---------|--------:|------:|------|
| `waitForTimeout` | 390 | 🟡 | 需推断 API endpoint |
| `attachScreenshot` | 239 | 🟡 | 需重构为 withStep |
| `login_call` | 114 | 🟢 | auto-fix (删除) |
| `setAdminPermissions_call` | 108 | 🟢 | auto-fix (删除) |
| `el_table_locator` | 60 | 🔴 | 需 POM 替换 |
| `pw_import` | 40 | 🟢 | auto-fix |
| `auth_import` | 39 | 🟢 | auto-fix (删除) |
| `navigateAndWaitForPage` | 22 | 🟢 | auto-fix |
| `page_goto` | 17 | 🟢 | auto-fix |
| `el_tabs_item` | 9 | 🟡 | 需 openTab() |
| `search_input` | 5 | 🟡 | 需 search() |

---

## 五、试点建议 (P0 优先)

### Top 10 最易迁移的 v1 spec (建议先做这 10 个)

1. **menu-bo-linker.spec.js** (moderate, 2 手动, 估时 15-30 min (1-2 POM 重构))
2. **permission-explainer.spec.js** (moderate, 2 手动, 估时 15-30 min (1-2 POM 重构))
3. **debug-column-config.spec.js** (moderate, 1 手动, 估时 15-30 min (1-2 POM 重构))
4. **intent-apis.spec.js** (moderate, 0 手动, 估时 15-30 min (1-2 POM 重构))
5. **role-intents.spec.js** (moderate, 0 手动, 估时 15-30 min (1-2 POM 重构))
6. **data-permission-config.spec.js** (moderate, 0 手动, 估时 15-30 min (1-2 POM 重构))

### 迁移步骤 (单个 spec):
```
1. 备份原 spec (git commit 前)
2. 改 import: @playwright/test → auto-fixtures.js
3. 删 v1 helpers import (login, setAdminPermissions, etc.)
4. 在 test 参数加: { page, devLogin, navigateTo, isolation, waitForApiFn, withStep }
5. 删 await login(page) + await setAdminPermissions(page)
6. await navigateAndWaitForPage(...) → await navigateTo(...)
7. await attachScreenshot → withStep 包裹原代码块
8. await page.waitForTimeout → await waitForApiFn(已知 API) 或删除
9. page.locator(".el-table") → 用 POM (archData.getRowCount() 等)
10. 跑 python e2e/scripts/check_v2_compliance.py <spec>
11. 跑 npx playwright test <spec> --retries=0 --project=features 验证
```

---

## 六、自动化程度评估

| 步骤 | 自动程度 | 工具 |
|------|---------|------|
| 1. import 替换 | 🟢 100% | sed/Python regex |
| 2. 删除 login/setAdminPermissions | 🟢 100% | sed/Python regex |
| 3. navigateAndWaitForPage → navigateTo | 🟢 100% | sed/Python regex |
| 4. page.goto → navigateTo | 🟢 100% | sed/Python regex |
| 5. waitForTimeout → waitForApiFn | 🟡 50% | 需 API 信息 |
| 6. attachScreenshot → withStep | 🟡 30% | 需上下文分析 |
| 7. .el-table → POM | 🔴 10% | 需业务理解 |
| 8. .el-tabs → openTab | 🟡 70% | 部分可自动 |

**结论**: 简单迁移 70% 可自动,POM 重构需人工 (核心价值)。
