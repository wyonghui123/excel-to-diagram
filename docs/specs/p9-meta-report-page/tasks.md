# P9 实施任务清单（MetaReportPage）

> 对应规格：`docs/specs/p9-meta-report-page/spec.md`
> 状态：**已完成 · 已验证**　｜　原则：按序执行，每阶段可独立验证

---

## 阶段 1：配置模型与解析

| ID | 任务 | 文件 | 验收 | 状态 |
|---|---|---|---|---|
| P9-1 | 新增 `UIReportFilterConfig / UIReportKpiConfig / UIReportChartConfig / UIReportTableConfig / UIReportDrilldownConfig / UIReportConfig`；`UIViewConfig` 增加 `report` | `meta/core/models_ui_config.py` | 缺省字段可构造；`UIViewConfig` 能承载 report | 完成 |
| P9-2 | `parse_ui_report_config`：YAML `field` → `key`，解析 filters/kpis/chart/table/drilldown | `meta/core/yaml_loader.py` | `inventory_balance.yaml` 加载出完整 report | 完成 |
| P9-3 | `_is_config_empty` 把 `report` 计入非空判断 | `meta/services/view_config_service.py` | 仅声明 report 的 BO 不被判空覆盖 | 完成 |

---

## 阶段 2：首个消费方与菜单

| ID | 任务 | 文件 | 验收 | 状态 |
|---|---|---|---|---|
| P9-4 | `inventory_balance` 增加 `ui_view_config.report`（endpoint / 7 filters / 2 KPIs / bar / table / drilldown） | `meta/schemas/inventory_balance.yaml` | view-config API 返回 `data.report` | 完成 |
| P9-5 | `menu.yaml` 的 `page_type` 枚举增加 `report` | `meta/schemas/menu.yaml` | 菜单校验通过 | 完成 |
| P9-6 | 迁移 `v225__inventory_aging_report_menu.py`：新增 `inventory-aging-report` 菜单；`show_in_sidebar=1`；已存在行幂等 UPDATE | `meta/migrations/v225__inventory_aging_report_menu.py` | `/api/v1/menu-permission/visible` 下发该菜单 | 完成 |

**红线**：报表菜单必须 `show_in_sidebar=1`，否则不下发 → 无路由 → 页面空白。

---

## 阶段 3：前端

| ID | 任务 | 文件 | 验收 | 状态 |
|---|---|---|---|---|
| P9-7 | `MetaReportPage.vue`：加载 report 配置、筛选映射、参数构造、KPI、表格分页、钻取 | `src/views/MetaReportPage.vue` | 选组织后请求 200，KPI/表格/图表渲染 | 完成 |
| P9-8 | `ReportBarChart.vue`：ECharts 按需引入（含 `TitleComponent`）、ResizeObserver、销毁 | `src/components/common/MetaReportPage/ReportBarChart.vue` | 无 `Component title is used but not imported` | 完成 |
| P9-9 | 动态路由注册 `report` 页型，`_buildProps` 注入 `objectType` | `src/router/dynamicRoutes.js` | `/inventory-aging` 命中 `MetaReportPage` | 完成 |
| P9-10 | `FilterBar` 新增 `date` 分支（`DateTimePicker`，只到日） | `src/components/common/FilterBar/FilterBar.vue` | 截止日期可选择/清空，回传 `YYYY-MM-DD` | 完成 |

---

## 阶段 4：验证与文档

| ID | 任务 | 命令 / 证据 | 结果 | 状态 |
|---|---|---|---|---|
| P9-11 | 后端配置回归 | `python d:\filework\test.py --single meta/tests/test_report_view_config.py` | 9 passed | 完成 |
| P9-12 | 全对象视图配置回归 | `python d:\filework\test.py --single meta/tests/test_runtime_view_config_engine.py` | 15 passed | 完成 |
| P9-13 | 前端容器单测 | `npx vitest run src/views/__tests__/MetaReportPage.spec.js` | 14 passed | 完成 |
| P9-14 | 前端图表单测 | `npx vitest run src/components/common/MetaReportPage/__tests__/ReportBarChart.spec.js` | 5 passed | 完成 |
| P9-15 | 浏览器实机验证 | 菜单 → 路由 → 筛选 → `GET /api/v1/inventory-aging/report?org_id=1&group_by=balance` 200 → 2 KPI + canvas + 8 列表头，控制台无错误 | 通过 | 完成 |
| P9-16 | 规格文档 | 本目录 `spec.md` + `tasks.md` | 入库 | 完成 |

---

## DoD 检查

- [x] 新增报表只需改 YAML + 菜单迁移，前端零改动
- [x] 配置缺失 / 接口失败均有可见错误提示，不白屏
- [x] 筛选空值不进入请求参数，日期统一 `YYYY-MM-DD`
- [x] 筛选状态原地更新（不使用 `v-model` 绑定 reactive）
- [x] 图表实例卸载时 `dispose`
- [x] 钻取受 `only_when_group_by` 约束
- [x] 后端 / 前端测试与实机验证全部通过
