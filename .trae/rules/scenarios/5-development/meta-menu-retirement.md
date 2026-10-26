---
alwaysApply: false
description: "下架 / 新增元数据对象的导航菜单时查阅此规则。给出独立菜单是否合适的判据、init_menu_permissions 的 UPSERT 不删行事实、步骤 7.5/7.6 清理因 commit 位置错误而假成功的根因、以及用 migration 兜底退役存量菜单行的标准做法。"
globs: "meta/scripts/init_menu_permissions.py,meta/migrations/*.py,meta/schemas/*.yaml"
---

# 元数据菜单生命周期规范（v2026.10.23）

> **来源**：2026-10-23 下架「客户档案 / 供应商档案」两个独立菜单实战
> **核心教训**：**init 脚本的清理输出是「假成功」** —— 打印「清理了 N 条」不等于 DB 里真删了

---

## 一、对象该不该做独立菜单：三层判据

### 1.1 先问「这个对象是哪一层的」

| 层 | 例子 | 入口形态 |
|----|------|---------|
| 主体实体（identity anchor） | `party` / `person` | 独立菜单 ✅ |
| 关系（连接两个主体） | `party_relation` | 收进主体的 tab / 分区 |
| 关系侧属性（挂在关系上 1:1） | `customer_account` / `vendor_account` | 收进**关系**的详情页分区 |

### 1.2 判据

1. 对象与某个已有对象是 **1:1**（靠唯一外键锚定）⇒ 它是**那一层的属性**，不是并列实体。
2. 若**上一层**（如 `party_relation`）自己都没有独立菜单 ⇒ 比它更下一层的更不该有。
3. 1:1 明细面做独立菜单 = 用户面对一个「只能通过某个关系才能到达」的列表，
   既要选关系才能找到数据，又多一个菜单层级 —— 平级入口属**放错层**。

> **本项目先例**：`party_relation` 自己已于 2026-10-17 下架独立菜单、收进业务伙伴页第三 tab
> （理由：关系是连接两个 party 的边，平级入口属放错层）。

### 1.3 下架 ≠ 可以没有 UI 配置

**对象不做独立菜单，仍然必须有完整的 `ui_view_config` 三态**（list / form / detail）。
原因：

- 对象仍然可能被 `MetaListPage` / 抽屉 / 关联分区以**别的入口**渲染；
- 缺 `list.columns` ⇒ 兜底推导 ⇒ **裸 ID 列**；
- 缺 `form.sections` ⇒ **编辑抽屉零字段**。

⇒ **下架菜单和补 UI 配置是两件事，不能互相替代。**
详见 [meta-ui-view-config.md](./meta-ui-view-config.md)。

---

## 二、`init_menu_permissions.py` 的三个事实

### 2.1 事实一：UPSERT 不删行

脚本对 `menus` / `menu_permissions` 只做 `INSERT ... ON CONFLICT DO UPDATE`。
**从声明里删掉一个菜单，不会删掉 DB 里已存在的行。**
⇒ 光改 init 脚本，存量环境里的旧菜单**依然在侧边栏**。

### 2.2 事实二：步骤 7.5 / 7.6 的清理是**假成功**（重要）

脚本 L1555-1595 的「冗余清理」逻辑本身是对的，但：

```
L1553   conn.commit()          ← 最后一次 commit 在这里
L1555   步骤 7.5 清理 menu_permissions  ← DELETE 在 commit 之后
L1575   步骤 7.6 清理 menus 导航表     ← DELETE 在 commit 之后
L1595   print("清理了 N 条冗余导航菜单")  ← 照样打印成功
L1683   conn.close()           ← 未提交改动被 SQLite 回滚
```

**后果**：脚本打印「清理了 N 条冗余导航菜单」，但事务从未提交，
`conn.close()` 时这些 DELETE 被**回滚** —— DB 里的行一条没少。
⇒ **全系统所有 stale 菜单/权限清理都不生效**（不只本次这两个）。

### 2.3 事实三：症状是「静默」，不是报错

- 无异常、无非零退出码、日志正常；
- 只有直接查 DB 才能发现行还在；
- **只靠脚本输出判断成败会漏掉**（属 L5「exit 0 不等于成功」家族，但这里是 DB 事务层）。

### 2.4 排查手法（复现时照做）

```python
# 1) 跑脚本，记下它打印的「清理了 N 条」
# 2) 不信输出，直接查库
conn.execute("SELECT menu_code, is_active FROM menus WHERE menu_code = ?", (code,)).fetchone()
# 3) 对照 HEAD 版本，确认不是本次改动引入
# git show HEAD:meta/scripts/init_menu_permissions.py
```

---

## 三、标准做法：用 migration 兜底退役存量菜单行

**不要**靠改 init 脚本去删存量行（UPSERT 不删行 + 清理假成功，两条都堵死）。
用 migration 做**下架**（`is_active = 0`）而不是物理删除：

### 3.1 为什么是 `is_active = 0` 而不是 DELETE

- 物理删除会连带丢失菜单的角色绑定、排序、层级；
- `is_active = 0` 可**幂等重放**、可**回滚复原**（downgrade 把 `is_active` 改回 1）。

### 3.2 migration 五件套（照 `v093` 模板）

```python
RETIRED = [('customer-account-management', 61), ('vendor-account-management', 62)]
NEW_MENU_CODE = 'party-management'      # 收纳入口，新菜单必须已启用

def _do_upgrade(conn):
    # ① 先校验收纳入口已启用（否则下架后用户无处可去）
    row = conn.execute("SELECT is_active FROM menus WHERE menu_code = ?", (NEW_MENU_CODE,)).fetchone()
    assert row and row[0] == 1
    # ② 下架旧菜单（保留行）
    for code, _sort in RETIRED:
        conn.execute("UPDATE menus SET is_active = 0 WHERE menu_code = ?", (code,))
    # ③ 清理孤儿 menu_permissions
    for code, _ in RETIRED:
        conn.execute("DELETE FROM menu_permissions WHERE menu_code = ?", (code,))
    conn.commit()                        # ← 自己 commit，不依赖外层

def _do_downgrade(conn):
    for code, sort in RETIRED:
        conn.execute("UPDATE menus SET is_active = 1, parent_menu = ?, sort_order = ? WHERE menu_code = ?", ...)
    conn.commit()

def verify(conn):
    # 断言：新菜单启用 + 旧菜单 is_active=0 + menu_permissions 无孤儿行
```

### 3.3 必须断言的 3 件事

1. **收纳入口已启用**（否则下架后功能无处可达）；
2. 旧菜单 `is_active = 0`；
3. `menu_permissions` / `permission_set_menu_permissions` 里**无孤儿行**。

第 3 条最容易漏 —— 只置 `is_active=0` 而留着权限行，角色侧仍可能看到残缺入口。

### 3.4 幂等要求

migration 必须**可重复执行**：第二次跑应打印 `[SKIP]` 而不是报错或重复改。
自检方式：连跑两次，比对 DB 终态一致。

---

## 四、动作权限码（菜单/列表动作通用）

`permissions` 表实有形态是**双段式** `{bo}:{bo}_{action}`：

```
customer_account:customer_account_create   ✅ 命中
customer_account:create                    ❌ 命中数 0 ⇒ 非 admin 看不到按钮
```

单段式不会报错，只会**静默不显示按钮**。写之前先查 `permissions` 表实际值。

---

## 五、自检清单

```
□ 这个对象是主体实体，还是挂在别人身上的属性？（决定要不要独立菜单）
□ 上一层的对象有独立菜单吗？（没有 ⇒ 更下一层也不该有）
□ 下架菜单后，对象的 ui_view_config 三态补齐了吗？（list/form/detail）
□ init 脚本里删掉了对应 menu_code 声明吗？（防它被重新生成）
□ 存量环境靠 migration 下架吗？（UPSERT 不删行 + 清理假成功）
□ migration 幂等吗？连跑两次 DB 终态一致吗？
□ menu_permissions / permission_set_menu_permissions 有孤儿行吗？
□ 权限码是双段式吗？已查 permissions 表确认？
```

---

## 六、相关代码

- 初始化脚本：[init_menu_permissions.py](file:///d:/filework/excel-to-diagram/meta/scripts/init_menu_permissions.py) L1553（commit）/ L1555-1595（假成功清理）
- 迁移模板：[v093__party_momp_page.py](file:///d:/filework/excel-to-diagram/meta/migrations/v093__party_momp_page.py)
- 本次迁移：[v098__retire_account_menus.py](file:///d:/filework/excel-to-diagram/meta/migrations/v098__retire_account_menus.py)
- 视图配置规范：[meta-ui-view-config.md](./meta-ui-view-config.md)

---

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|---------|
| 2026-10-23 | AI Assistant | 初版：独立菜单是否合适的三层判据、下架 ≠ 无 UI 配置、init 脚本 UPSERT 不删行 + 步骤 7.5/7.6 清理假成功（commit 位置根因）、migration 退役菜单行标准做法与三条必断言、自检清单 |
