# Tasks: 预存 E2E 失败修复

- [x] T1 `e2e/page-objects/ArchDataPage.js#openTab` 支持 `.momp-tab-btn`（保底 el-tabs）
  - 验证：`npx playwright test --project=features e2e/features/pagination.spec.js e2e/features/deep-insert.spec.js`（retries=0）
- [x] T2 `e2e/features/audit-log.spec.js#switchToAuditLogTabAndAssertLogs` 加入 `.anchor-tab:has-text("操作日志")`
  - 验证：`... e2e/features/audit-log.spec.js -g "F07-F09"` 桌面 + mobile-features
- [x] T3 `e2e/helpers/data-finder.js#createProductWithVersion` 版本名改 `V1.0`
  - 验证：`... e2e/features/product-version-crud.spec.js -g "V03|V05"`
- [x] T4 `e2e/features/product-version-crud.spec.js` V03/V05 解构 `{ product }`；V06 改 `page.request`；V07 全部改 `page.request` 并补 product 必填字段
  - 验证：`... e2e/features/product-version-crud.spec.js` 桌面 + mobile-features
- [x] T5 `e2e/features/delete-validation-ui.spec.js` C01 searchTerm 取 `ctx.pv`；C03 code 用 `generateCode`；C02 重写为「自建 group + 关联 member + 清理关联」
  - 验证：`... e2e/features/delete-validation-ui.spec.js` 桌面 + mobile-features
- [x] T6 汇总：失败清单、改动清单、遗留产品缺陷（若有），不 commit
  - 桌面 features：23 passed / 6 skipped / 0 failed
  - 移动 mobile-features：21 passed / 8 skipped / 0 failed
  - 遗留（仅报告/已授权修复）：删除 C01 文案已由 PM 授权改为友好提示（action_executor.py `_do_delete`）；`/api/v1/roles` 迁移后无列表接口（用例已改自建数据）；产品详情「版本列表」无行级操作列（V03 走批量删除入口不可用，保持 skip）
