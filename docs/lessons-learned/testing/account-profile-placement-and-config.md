# 元数据档案落点裁定 —— 从独立菜单改为关系详情页分区

> **记录日期**: 2026-10-23
> **痛点来源**: 用户发现「客户档案 / 供应商档案」作为独立菜单不合适，问「与业务伙伴是什么关系」
> **核心教训**: **对象保留、入口重选** —— 1:1 明细面不该有平级菜单；**下架菜单 ≠ 可以没有 UI 配置**

---

## 问题描述

`customer_account`（客户档案）与 `vendor_account`（供应商档案）两个元数据对象：

- 2026-10-06 按 spec 建骨架，当时对象是**结构占位**，无实际业务价值字段；
- 同批在 `init_menu_permissions.py` 里手工声明了两个独立菜单
  （`customer-account-management` / `vendor-account-management`）；
- 用户实测后提出三点质疑：
  1. 打开菜单后能看到**裸 ID 列**（`id` / `created_at` 一堆技术字段）；
  2. 档案对象作为**独立菜单项**是否合适；
  3. 它跟现在的「业务伙伴」是什么关系。

---

## 一、落点裁定：三层链路

```
party                身份锚（谁）
  └─ party_relation  我方组织 × 对手方 × 角色   ← 关系的"边"
       └─ customer_account / vendor_account   关系侧档案 1:1
```

| 层 | 例子 | 入口 |
|----|------|------|
| 主体实体 | `party` | 独立菜单 ✅ |
| 关系 | `party_relation` | 收进业务伙伴页第三 tab |
| 关系侧属性（1:1） | `customer_account` / `vendor_account` | 收进**关系**详情页的关联分区 |

**关键先例**：`party_relation` 自己已于 **2026-10-17** 下架独立菜单、收进业务伙伴页第三 tab，
理由是「关系是连接两个 party 的边，平级入口属放错层」。
比关系**再下一层**的档案做平级菜单，更说不通。

### 落点 A（用户选定）：不做菜单，进 `party_relation` 详情页关联分区

档案与 `party_relation` 是 1:1（`relation_id` 唯一），是**关系侧属性**而非与 `party` 并列的主体实体。
⇒ 两个档案分区声明在 `party_relation.yaml` 的 `detail.facets` 下。

---

## 二、顺带修掉两处真实缺陷

### 2.1 裸 ID 列

**根因**：`/api/v2/meta/<obj>/ui-config` 端点走 [config_builder.py](file:///d:/filework/excel-to-diagram/meta/core/ui_config/config_builder.py) L70-75 的**兜底推导**：

```python
if not _ui_view_config_has_renderable_form(config.get('ui_view_config')):
    _built = view_config_service.get_or_build_view_config(object_type, view_name)
    config['ui_view_config'] = _make_json_safe(_built)
```

此前两个 yaml 只写了 `skip_auto_menu: true`，**没有 `list.columns`** ⇒ 触发兜底推导
⇒ 该推导按 `ui.visible` 收**全部字段** ⇒ 把技术主键 `id`、`created_at`、审计字段全渲染成列。

**修法**：显式声明 `list.columns`（4 列：`name` / `customer_type` / `description` / `created_at`）。

> **判据不是「yaml 写了」**，而是 `_ui_view_config_has_renderable_form(raw) == True`
> （为 True 就不再走兜底）。实测两个对象均为 `True`，裸 `id` 未混入列集合。

**列集合刻意不含 `relation_id`**：1:1 明细面，该列恒等于父 id，纯冗余。

### 2.2 编辑态空白

**根因**：`DetailPage.vue` 的 `computedSections` 两处渲染来源不同：

| 来源 | 行为 |
|------|------|
| `ui_view_config.form.sections` | 编辑态抽屉**唯一**来源 |
| `detail.facets[].fieldGroup` | 编辑态被 `if (isEditing) continue` 跳过 |

此前既无 `form` 也无 `detail` ⇒ 新建/编辑抽屉**零字段**，只剩「保存/取消」。

**修法**：三个 yaml 同时补齐 `list` / `form` / `detail` 三态。

---

## 三、为什么必须走 `customFetcher`（跨行数据泄漏风险）

`AssociationSection.vue` 的平台关联端点过滤列**写死**：

```js
const parentKey = `${props.objectType}_id`   // party_relation ⇒ party_relation_id
```

而两个档案表的列名是 `relation_id` ⇒ **列名不匹配** ⇒ 后端忽略该条件返回**全量**
⇒ 一个关系详情页会列出**所有人**的档案。

> **这不是显示问题，是数据泄漏问题。**
> 凡是子表外键列名 != `{父对象类型}_id`，都必须改走 `customFetcher` 精确查。

`customFetcher: relation_accounts` 分支按 `relation_id: props.objectId` 精确取数，
并带 `_relationAccountsVersion` 序号守卫防竞态。

### 附带发现：`detail.tabs` 与 `detail.facets` 不是同一套闸门

| 分支 | 行号 | 动作处理 |
|------|------|---------|
| `detail.tabs` | L776-870 | `safeActions` 过滤（readonly 时只留 `list` / `create`） |
| `detail.facets` | L871-932 | **不**做过滤，`f.actions` 原样透传 |

`party_relation.yaml` 的 `detail` 下**只有 `facets`、没有 `tabs`** ⇒ 走 facets 分支
⇒ 该分支对带 `customFetcher` 的 facet 已放行闸门（L901-905）⇒ `create` 动作原样透传。

---

## 四、下架菜单：init 脚本靠不住，必须 migration 兜底

### 4.1 两个事实

1. **init 脚本的 UPSERT 不删行** —— 从声明里删掉 `menu_code`，DB 里已存在的行**依然在**。
2. **步骤 7.5 / 7.6 的清理是假成功** —— `conn.commit()` 在 **L1553**，
   而 DELETE 在 **L1555** 之后 ⇒ 脚本退出时未提交改动被 SQLite **回滚**，
   但照样打印「清理了 N 条冗余导航菜单」。

> **这意味着全系统所有 stale 菜单/权限清理都不生效**，不只本次这两个。
> 本次未改这个共享脚本（避免全系统 stale 菜单被物理删除的连带影响），
> 改为在 migration 里自己 commit + 额外清 `menu_permissions` 孤儿行。

### 4.2 migration 的做法

`v098__retire_account_menus.py` 照 `v093` 模板：

- **下架而非物理删除**（`is_active = 0`）—— 幂等、可回滚复原；
- 先校验收纳入口 `party-management` 已启用，否则下架后用户无处可去；
- 额外清理 `menu_permissions` 孤儿行（只置 `is_active=0` 而留着权限行，角色侧仍会看到残缺入口）；
- `verify()` 断言三件事：新菜单启用 + 旧菜单 `is_active=0` + `menu_permissions` 无孤儿行。

实测：`[RETIRE] ×2 → [CLEAN] menu_permissions 2 条 → verify PASS`；
二次执行 `[SKIP] ×2 → verify PASS`（幂等）。

---

## 五、动作权限码必须是双段式

`permissions` 表实有形态是 `{bo}:{bo}_{action}`：

```
customer_account:customer_account_create   ✅ 命中
customer_account:create                    ❌ 命中数 0 ⇒ 非 admin 看不到按钮
```

单段式**不报错**，只是静默不显示按钮 ⇒ 排查时先查 `permissions` 表实际值。
（口径与 `menu_auto_generator._derive_permissions_from_bindings` 一致。）

---

## 六、结果

| 项 | 结果 |
|----|------|
| `test_customer_account.py` | 48 passed |
| `test_vendor_account.py` | 58 passed |
| `test_f2_party_relation.py` | 28 passed（含新增 6 个） |
| `test_menu_auto_generator.py` / `test_field_policy.py` | 11 / 51 passed |
| `useMetaList.scenarios.spec.js` | passed |
| `npx eslint AssociationSection.vue` | 0 errors / 5 warnings（均在我改动之外的既有代码） |
| 配置下发链路静态验证 | 两个对象 `has_renderable_form == True`；列集合正确；裸 `id` 未混入；两个 facet 的 `type/association/customFetcher/readonly/actions` 原样保留 |

**未做**：浏览器端到端验证（尚未起服务用 PlaywrightCLI 实测「业务伙伴页 → 往来关系 tab → 行详情 → 两个档案分区渲染 + 新建/编辑」）。
静态链路（yaml → loader → 模型 → `_make_json_safe` → DetailPage 闸门 → AssociationSection 分支）已逐段核对通过。

---

## 经验总结

1. **1:1 明细面不做独立菜单** —— 判据：与已有对象 1:1 且上一层自己都没有独立菜单 ⇒ 更下一层更不该有。
2. **下架菜单 ≠ 可以没有 UI 配置** —— 对象仍会被抽屉/分区渲染，`list/form/detail` 三态仍要补齐。
3. **「YAML 写了」≠「界面生效」** —— 判据是后端真实下发的 JSON 形状 + `has_renderable_form == True`。
4. **子表外键列名 != `{父对象类型}_id` ⇒ 必须 `customFetcher`**，否则是**跨行数据泄漏**，不是显示问题。
5. **脚本输出 ≠ 事实** —— DB 事务未提交会被回滚；清理类操作必须直接查 DB 验证。
6. **init 脚本 UPSERT 不删行** —— 存量菜单退役必须靠 migration（下架 `is_active=0` + 清孤儿权限行 + verify 断言）。
7. **权限码双段式** —— 单段式静默失效，非 admin 看不到按钮。
8. **`detail.tabs` 与 `detail.facets` 闸门不同** —— 声明前先确认父对象走哪个分支。

---

## 相关代码

- 客户档案：[customer_account.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/customer_account.yaml)
- 供应商档案：[vendor_account.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/vendor_account.yaml)
- 关系分区声明：[party_relation.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/party_relation.yaml)
- 自定义取数器：[AssociationSection.vue](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/AssociationSection.vue)
- 详情页分区计算：[DetailPage.vue](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailPage.vue) L636-932
- 兜底推导入口：[config_builder.py](file:///d:/filework/excel-to-diagram/meta/core/ui_config/config_builder.py) L7-24 / L70-75
- 退役迁移：[v098__retire_account_menus.py](file:///d:/filework/excel-to-diagram/meta/migrations/v098__retire_account_menus.py)
- 原始 spec：[2026-10-06-customer-account-profile-design.md](file:///d:/filework/excel-to-diagram/docs/superpowers/specs/2026-10-06-customer-account-profile-design.md)

---

**最后更新**: 2026-10-23
