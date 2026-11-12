# P9 元数据驱动报表页（MetaReportPage）实现规格

> 状态：**已实施 · 已验证**
> 日期：2026-11-06
> 关联：`docs/specs/p8-inventory-aging-model/spec.md`（首个消费方：库存库龄）

---

## 0. 结论先行

1. **报表页也是元数据**：报表的标题、数据接口、筛选器、KPI、图表、表格列、钻取全部声明在 BO 的 `ui_view_config.report` 中，前端不写任何业务字段名。
2. **新增第 6 个视图段**：在既有 `list / detail / form / filter / hub` 之外新增 `ui_view_config.report`，复用同一条 `GET /api/v1/meta/{objectType}/view-config/{viewName}` 通道，不新增配置 API。
3. **新增第 4 种动态页型**：`menu.page_type = report` → `MetaReportPage.vue`，与 `object_list` / `object_detail` / `multi_object_hub` 同一套动态路由机制。
4. **报表 v1 只做只读分析页**：`bar` 图表 + KPI 卡 + 客户端分页表格 + 可选钻取抽屉；不做导出、不做保存视图、不做多图表布局。
5. **第一个落地场景**：`inventory_balance` 的库存库龄报表（P8），读取 `/api/v1/inventory-aging/report`。

---

## 1. 背景与目标

P8 交付了库存库龄的后端计算与 thin API，但前端没有承载页。若为每个报表手写一个 Vue 页面，会重复出现：

- 筛选器与接口参数对不上（手写 key、手写默认值）；
- 表格列与后端返回字段漂移；
- 菜单、路由、权限、面包屑各写一遍；
- 每加一张报表就要改前端代码并重新发版。

目标：**用声明式配置承载“只读分析型页面”**，让新增报表只需写 YAML + 一条菜单迁移。

---

## 2. 范围

### 2.1 In Scope

| 能力 | 说明 |
|---|---|
| `ui_view_config.report` | 标题/描述、endpoint、filters、kpis、chart、table、drilldown |
| 配置解析 | `parse_ui_report_config` 把 YAML 映射为 dataclass，缺省字段有默认值 |
| 配置下发 | view-config API 的 `data.report`，与 list/detail/form 同响应 |
| 动态路由 | `page_type: report` 注册到 `MetaReportPage`，注入 `objectType` |
| 筛选栏复用 | 复用 `FilterBar`，新增 `date` 类型分支 |
| 图表 | ECharts 柱状图，按需引入 |
| 表格 | 客户端分页，number/date 格式化 |
| 钻取 | 行点击按 `param_map` 调明细接口，抽屉展示 |
| 菜单 | v225 迁移新增 `inventory-aging-report` |

### 2.2 Out of Scope

- 图表类型扩展（line / pie / table-only 组合）
- 服务端分页、导出 Excel、订阅推送
- 报表配置的可视化编辑（仍以 YAML 为唯一真源）
- 多数据源 join、指标计算下推到前端

---

## 3. 配置契约

### 3.1 YAML 形态（以 `inventory_balance.yaml` 为例）

```yaml
ui_view_config:
  report:
    title: 库存库龄
    description: 按余额行最早入库日分桶；空日期=期初未回填/负库存/无库存
    endpoint: /api/v1/inventory-aging/report
    filters:
      - { field: org_id, label: 库存组织, type: value_help, target_type: org, required: true }
      - { field: stock_status, label: 库存状态, type: select }
      - { field: as_of, label: 截止日期, type: date }
      - { field: group_by, label: 汇总维度, type: select, default: balance, options: [...] }
    kpis:
      - { label: 在手数量, field: total_qty, format: number }
    chart: { type: bar, title: 库龄分布, data_field: summary, category_field: bucket, value_field: qty }
    table:
      data_field: rows
      page_size: 20
      row_key: [org_id, location_id, item_id]
      columns:
        - { field: qty_on_hand, label: 在手数量, format: number }
        - { field: first_received_date, label: 最早入库日期, format: date }
    drilldown:
      endpoint: /api/v1/inventory-aging/detail
      title: 库龄明细
      only_when_group_by: balance
      param_map: { org_id: org_id, location_id: location_id, as_of: as_of }
```

### 3.2 数据模型（`meta/core/models_ui_config.py`）

| dataclass | 关键字段 |
|---|---|
| `UIReportFilterConfig` | `key`（YAML 里写 `field`）、`label`、`type`、`required`、`default`、`options`、`target_type` |
| `UIReportKpiConfig` | `label`、`field`、`format` |
| `UIReportChartConfig` | `type`（v1 仅 bar）、`title`、`data_field`、`category_field`、`value_field` |
| `UIReportTableConfig` | `data_field`、`page_size`、`row_key`、`columns` |
| `UIReportDrilldownConfig` | `endpoint`、`title`、`only_when_group_by`、`param_map` |
| `UIReportConfig` | `title`、`description`、`endpoint`、`method`、上述各段 |

`UIViewConfig` 增加 `report` 字段；`ViewConfigService._is_config_empty` 同步把 `report` 计入“非空”，避免只有报表段的 BO 被判为空后被自动生成逻辑覆盖。

### 3.3 API 响应

```json
{ "success": true, "data": { "list": {...}, "detail": {...}, "form": {...}, "report": {...} } }
```

前端只读 `data.report`；缺失该段时页面展示“对象 X 未声明 ui_view_config.report”。

---

## 4. 后端链路

```
BO YAML
  └─ yaml_loader.parse_ui_report_config
       └─ UIViewConfig.report
            └─ ViewConfigService.get_or_build_view_config
                 └─ GET /api/v1/meta/{objectType}/view-config[/{viewName}]
```

- `meta/schemas/menu.yaml`：`page_type` 枚举新增 `report`。
- `meta/migrations/v225__inventory_aging_report_menu.py`：写入菜单行
  `menu_code=inventory-aging-report`、`menu_path=/inventory-aging`、`page_type=report`、
  `primary_object_type=inventory_balance`、`parent_menu=inventory-balance-management`、
  `required_permissions=["inventory_balance:inventory_balance_read"]`、`sort_order=7`。

**菜单可见性是硬前置**：`/api/v1/menu-permission/visible` 只下发 `show_in_sidebar=1` 的菜单。v225 初版误写为 `0`，导致前端无路由、页面空白；迁移中已对已存在行做幂等修正：

```python
conn.execute("UPDATE menus SET show_in_sidebar=1, is_active=1 WHERE menu_code=?", (MENU['menu_code'],))
```

**迁移建的菜单必须在 init 白名单**：`init_menu_permissions.py` 步骤 7.6 会物理删除 `auto_generated=0` 且未声明的菜单。该脚本已把白名单提升为模块级 `MIGRATION_OWNED_MENUS` 并登记 `inventory-aging-report`；否则每次服务启动/测试 setup 后菜单都会消失，而 `schema_migrations` 仍为 SUCCESS（记录与副作用漂移）。

---

## 5. 前端链路

### 5.1 动态路由（`src/router/dynamicRoutes.js`）

```js
const PAGE_TYPE_COMPONENTS = {
  object_list: () => import('@/views/GenericObjectList.vue'),
  object_detail: () => import('@/views/ObjectDetailPage.vue'),
  multi_object_hub: () => import('@/views/GenericTabContainer.vue'),
  report: () => import('@/views/MetaReportPage.vue'),
}
```

`_buildProps` 对 `object_list` / `report` 注入 `objectType = menu.primary_object_type`。

### 5.2 容器（`src/views/MetaReportPage.vue`）

| 职责 | 实现要点 |
|---|---|
| 加载配置 | `metaService.getViewConfig(objectType)`，读 `data.report`；支持 `pageConfig.report` 覆盖 |
| 筛选字段映射 | `value_help` → `valueHelpConfig = { source: { type:'bo', target_bo: target_type }, behavior:{}, presentation:{} }` |
| 筛选状态 | `reactive({})` + **原地合并**（`onFilterValuesChange`），不能用 `v-model` 给 reactive 常量赋值 |
| 请求参数 | `buildParams()` 跳过 `''/null/undefined`；`date/datetime` 统一转 `YYYY-MM-DD` |
| endpoint | `normalizeEndpoint` 去掉 `/api/v1` 前缀，交给 `apiV1` 命名空间 |
| KPI | 读响应顶层字段，`number` 用 `toLocaleString('zh-CN')` |
| 表格 | `data_field` 取行、客户端 `page_size` 分页、`row_key` 拼接 |
| 钻取 | `only_when_group_by` 不满足时不请求；`param_map` 先取行值、回退筛选值 |

### 5.3 图表（`src/components/common/MetaReportPage/ReportBarChart.vue`）

ECharts 5.5.1 按需引入，必须显式 `use` 用到的组件：

```js
import { BarChart } from 'echarts/charts'
import { GridComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([BarChart, GridComponent, TitleComponent, TooltipComponent, CanvasRenderer])
```

> 漏 `TitleComponent` 会在运行时抛 `Component title is used but not imported`，且只在配置了 `title` 时触发。

- `ResizeObserver` 自适应宽度；`onBeforeUnmount` 中 `disconnect` + `dispose`。
- `items` 深度 watch 触发 `setOption(option, true)` 全量替换。

### 5.4 筛选栏（`FilterBar.vue`）

新增 `field.type === 'date'` 分支，渲染 `DateTimePicker`（`:show-time="false"`、`size="md"`、`clearable`），回传 `YYYY-MM-DD` 字符串。

---

## 6. 验证证据

| 层 | 用例 / 证据 | 结果 |
|---|---|---|
| 后端配置 | `python d:\filework\test.py --single meta/tests/test_report_view_config.py` | 10 passed（含菜单白名单断言） |
| 后端全对象 | `--single meta/tests/test_runtime_view_config_engine.py` | 15 passed（含本次补齐 3 个 facade 视图的 list 列） |
| 后端迁移 | `--single meta/tests/test_migration_runner_verify.py` | 3 passed（verify dict 归一化） |
| 前端容器 | `npx vitest run src/views/__tests__/MetaReportPage.spec.js` | 14 passed |
| 前端图表 | `npx vitest run src/components/common/MetaReportPage/__tests__/ReportBarChart.spec.js` | 5 passed |
| 前端筛选 | `npx vitest run src/components/common/FilterBar/__tests__/FilterBar.spec.js` | 36 passed（含 `date` 分支 2 例） |
| 浏览器实机 | 菜单下发 → 路由注册 → 7 项筛选 → 选库存组织 → `GET /api/v1/inventory-aging/report?org_id=1&group_by=balance` 200 → 2 KPI + ECharts canvas + 8 列表头，控制台无错误 | 通过 |

---

## 7. 已知限制与后续

1. **图表只有 bar**：`UIReportChartConfig.type` 目前未做分支，新增 line/pie 需扩展 `ReportBarChart` 或新增组件。
2. **客户端分页**：服务端返回全量行，10 万行级别需要改用服务端分页。
3. **钻取仅支持余额行**：`only_when_group_by` 是单值约束，按物料/批次汇总时不开放明细。
4. **无导出**：报表数据导出未实现。
5. **配置无校验**：YAML 中写错 `data_field` 只会得到空表，不会报错；后续可加 schema 校验。
6. **`method` 未生效**：`UIReportConfig.method` 已建模，但前端固定 `apiV1.get`；报表接口当前均为 GET。
7. **跨库漂移需手工重放**：v225 记录为 SUCCESS 但菜单被删的库（历史工作树/旧快照），白名单修复不会自动补回，需重放 v225 或手工 INSERT；主库已重放。

---

## 8. 关键踩坑

| 现象 | 根因 | 修复 |
|---|---|---|
| 页面空白、无路由 | 菜单 `show_in_sidebar=0`，`/menu-permission/visible` 不下发 | 改 `1` + 对存量行 UPDATE |
| 选组织后仍 400 `INV_AGING_ORG_REQUIRED` | `v-model` 绑定 `reactive` 常量，赋值无效 | `:model-value` + `onFilterValuesChange` 原地合并 |
| ECharts `Component title is used but not imported` | 按需引入漏 `TitleComponent` | 补 `echarts.use` |
| `org_legal_entity has no list columns` 等存量失败 | YAML 只有 detail/facets 时配置非空，自动生成不介入 | 三个 facade 视图补齐 `ui_view_config.list` |
| 迁移记录 SUCCESS 但菜单行不存在 | `init_menu_permissions.py` 步骤 7.6 物理删除 `auto_generated=0` 且未在 `MIGRATION_OWNED_MENUS` 的菜单 | 白名单登记 `inventory-aging-report` + 重放 v225 |
| v224/v225 `verify=OK` 但实际失败 | `verify()` 返回 dict，`bool(dict)` 恒真 | `verify_migration` 归一化 `{'ok': bool}` |
