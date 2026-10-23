# 客户/供应商档案落点裁定 —— 从独立菜单改为关系详情页分区

> **日期**: 2026-10-23
> **现象**: 用户质疑「客户档案 / 供应商档案」作为独立菜单不合适，并指出打开后能看到裸 ID
> **根因**: 档案是 `party_relation` 之上的 1:1 明细面，被当成了与 `party` 并列的主体实体
> **结果**: 对象保留、入口重选 —— 两个独立菜单下架，改为 `party_relation` 详情页的两个关联分区
> **代价**: 顺带发现并修掉两个既有缺陷（裸 ID 列、编辑态空白）+ 一个既有脚本缺陷（init 清理假成功）

---

## TL;DR

`customer_account` / `vendor_account` 与 `party_relation` 是 **1:1**（`relation_id` 唯一），
是**关系侧属性**而非与 `party` 并列的主体实体；而 `party_relation` 自己已于 2026-10-17
下架独立菜单收进业务伙伴页第三 tab。比关系再下一层的档案做平级菜单，属**放错层**。

⇒ 选定**方案 A**：不做菜单，在 `party_relation.yaml` 的 `detail.facets` 声明两个关联分区，
由 `AssociationSection` 的 `customFetcher: relation_accounts` 分支按 `relation_id` 取数。
顺带把两个 yaml 的 `ui_view_config` 从「只有 `skip_auto_menu`」补齐为 list/form/detail 三态，
修掉裸 ID 列与编辑态空白两个缺陷。

---

## 问题时间线

| 时间 | 事件 |
|------|------|
| T0 | 用户实测后提出三点质疑：① 打开后能看到裸 ID；② 独立菜单是否合适；③ 与业务伙伴什么关系 |
| T0+ | 只读勘查：两个 yaml 的字段/菜单声明、`party_relation` 的 detail 结构、`AssociationSection` 四条既有分支、`DetailPage` 闸门 |
| T0+ | 确认「对象保留 / 独立菜单不合适 / 三层链路」⇒ 给出方案 A（关系详情页分区）与方案 B（业务伙伴页第四 tab） |
| T1 | 用户拍板「选 A」 |
| T1+ | 改 3 个 yaml + 1 个 Vue 组件 + init 脚本 + 新增迁移 + 补 19 个测试用例 |
| T2 | 实测发现 `init_menu_permissions.py` 步骤 7.5/7.6 的清理是**假成功**（commit 位置早于 DELETE） |
| T2+ | 改为由 `v098` migration 兜底退役存量菜单行（`is_active=0` + 清孤儿权限行 + verify 断言） |
| T3 | 回归全绿；静态验证配置下发链路逐段核对通过 |

---

## 根因技术细节

### 1. 裸 ID 列 —— 兜底推导吞掉了声明

`config_builder.py` L70-75：`_ui_view_config_has_renderable_form()` 为 False 时，
用 `view_config_service.get_or_build_view_config()` 覆盖 yaml 声明。
该推导按 `ui.visible` 收**全部字段** ⇒ 技术主键 `id`、`created_at`、审计字段全成列。

### 2. 编辑态空白 —— 两处渲染来源不同

`DetailPage.vue`：`form.sections` 是编辑态抽屉唯一来源；`detail.facets[].fieldGroup` 编辑态被跳过。
此前两态皆无 ⇒ 抽屉零字段。

### 3. 平台关联端点过滤列写死 ⇒ 数据泄漏

`AssociationSection.vue`：`associationFilters` 写死 `{props.objectType}_id`。
父对象是 `party_relation` ⇒ 得 `party_relation_id`，而档案表列名是 `relation_id`
⇒ 列名不匹配 ⇒ 后端忽略条件返回全量 ⇒ **一个详情页列出所有人的档案**。

### 4. init 脚本清理假成功 —— commit 位置

`init_menu_permissions.py`：`conn.commit()` 在 **L1553**，DELETE 在 **L1555** 之后
⇒ 脚本退出时未提交改动被 SQLite 回滚，但照样打印「清理了 N 条冗余导航菜单」。
⇒ **全系统所有 stale 菜单/权限清理都不生效**（不只本次这两个）。

### 5. 字段元直接复用进表单 —— `type: string` 没有控件

1:1 内联表单直接拿 `/ui-config` 的 `fields[].type` 喂 `MetaForm`，而 `MetaForm` 只认
`text` / `number` / `textarea` / `select` / `value_help` 等控件类型；schema 里 `name` 是
`type: string` ⇒ 落不到任何 `v-else-if` 分支且无兜底 ⇒ **只渲染 label、没有输入框**。
修法：字段元转表单字段时显式归一化（`string → text`）。

---

## 调试方法论：什么有效，什么无效

| 手段 | 有效性 | 说明 |
|------|--------|------|
| 读 YAML 文本确认"我写了" | ❌ 无效 | 生效判据是**后端真实下发的 JSON 形状**，不是 yaml 文本 |
| 只看 init 脚本输出 | ❌ 无效 | 打印"清理了 N 条"是假成功，必须直接查 DB |
| 用真实 loader + `_make_json_safe` 探针 | ✅ 决定性 | 直接看到 `has_renderable_form`、列集合、facet 形状 |
| 读 `config_builder.py` 兜底分支 | ✅ 决定性 | 一眼定位"裸 ID 列"的机制来源 |
| 对照 `git show HEAD:` 确认缺陷是否本次引入 | ✅ 决定性 | 区分"本次引入"与"既有缺陷" |
| 查 `permissions` 表实际值 | ✅ 决定性 | 确认权限码必须是双段式 |

---

## 测试缺口 & 改进

**已补**（19 个新用例）：

- `test_customer_account.py` — `TestNoStandaloneMenuButConfigComplete` 9 个
  （skip_auto_menu 仍 true / init 声明中不得再出现 menu_code 与 path / list.columns 精确四列 /
  排除 `id` / 排除 `relation_id` / form.sections / form 排除 relation_id / detail.facets / 权限双段式）
- `test_vendor_account.py` — 对称性 4 个
- `test_f2_party_relation.py` — `TestAccountSections` 9 个
  （两个分区已声明 / 必须用 customFetcher / 未声明平台 association / readonly + 仅 create /
  权限双段式 / cardinality=one / 无 pageSize / 按 role 互斥 / loader 解析新字段）

**验证结果与遗留缺口**：

1. **浏览器端到端验证（已补，PlaywrightCLI + 生产构建 preview）**：
   - role=客户的关系详情：只出现「客户档案」分区（描述列表 + 编辑），无「供应商档案」，分区内**无表格**；
   - role=供应商的关系详情：只出现「供应商档案」分区，空态「暂无档案」+「新建供应商档案」；
   - 客户档案编辑保存：改名 → DB `customer_accounts.name` 变更 → 详情回显 → 改回复原；
   - 供应商档案新建表单：字段齐全 +「取消/创建」，取消后回到空态。
2. **init 脚本的清理假成功未修** —— 全系统级缺陷，属共享脚本，本次刻意不动（避免全系统 stale 菜单被物理删除的连带影响）。
3. **`fetcher.spec.js` F1.3 / F2.2 两条断言已与实现脱节** —— 对 HEAD 版本做同一正则匹配**同样为 False**
   ⇒ 既有失败，不在本次范围内。

---

## 经验教训（跨项目适用）

1. **对象的"入口位置"由它在层级里的位置决定，不由它的独立价值决定**。
   1:1 明细面做平级菜单 = 多一个层级、少一条到达路径。
2. **"上一层自己都没有独立菜单"是最强的反证**。先看先例，再设计入口。
3. **下架菜单和补 UI 配置是两件事**。对象仍会被抽屉/分区渲染，三态仍要补齐。
4. **"YAML 里写了"不等于"界面生效"**。验证判据是后端真实下发的 JSON。
5. **平台关联端点的过滤列写死 ⇒ 子表外键列名不同时必须走 `customFetcher`**，
   否则不是显示问题而是**跨行数据泄漏**。
6. **脚本输出 ≠ 事实**。DB 事务未提交会被回滚；清理类操作必须直接查库验证。
7. **UPSERT 型 init 脚本删不掉存量行**。退役菜单行必须靠 migration（下架 + 清孤儿 + verify 断言 + 幂等）。
8. **权限码双段式**。单段式静默失效，非 admin 看不到按钮。

---

## 行动项

| # | 项 | 状态 |
|---|---|------|
| 1 | 两个 yaml 补齐 `ui_view_config` 三态 | ✅ 完成 |
| 2 | `party_relation.yaml` 声明两个档案关联分区 | ✅ 完成 |
| 3 | `AssociationSection` 新增 `relation_accounts` 分支（含竞态守卫） | ✅ 完成 |
| 4 | init 脚本移除两个菜单声明 | ✅ 完成 |
| 5 | `v098` migration 退役存量菜单行 | ✅ 完成 |
| 6 | 补 19 个测试用例 + 回归 | ✅ 完成 |
| 7 | 经验沉淀（全局 2 份规范 + 项目 1 份经验档） | ✅ 完成 |
| 8 | 浏览器端到端验证 | ✅ 完成（PlaywrightCLI + 生产构建 preview） |
| 9 | 修 `init_menu_permissions.py` 步骤 7.5/7.6 的 commit 位置 | ⏳ 未做（共享脚本，需 PM 决策） |
| 10 | 修 `fetcher.spec.js` F1.3 / F2.2 陈旧断言 | ⏳ 未做（既有问题，另行处理） |

---

## 相关文件清单

**改动（项目仓库，14 个文件，全部未 commit）**

- 元数据：[customer_account.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/customer_account.yaml)、
  [vendor_account.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/vendor_account.yaml)、
  [party_relation.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/party_relation.yaml)
- 前端：[AssociationSection.vue](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/AssociationSection.vue)
- 脚本/迁移：[init_menu_permissions.py](file:///d:/filework/excel-to-diagram/meta/scripts/init_menu_permissions.py)、
  [v098__retire_account_menus.py](file:///d:/filework/excel-to-diagram/meta/migrations/v098__retire_account_menus.py)
- 测试：`test_customer_account.py` / `test_vendor_account.py` / `test_f2_party_relation.py`
- 经验档：[account-profile-placement-and-config.md](file:///d:/filework/excel-to-diagram/docs/lessons-learned/testing/account-profile-placement-and-config.md)

**新增全局规范**

- [meta-ui-view-config.md](file:///d:/filework/.trae/rules/scenarios/5-development/meta-ui-view-config.md)
- [meta-menu-retirement.md](file:///d:/filework/.trae/rules/scenarios/5-development/meta-menu-retirement.md)

**临时产物**：已清理（`architecture.db.v098bak` / `_chk.py` / `_probe*.py`）
