# 元数据对象迁移后测试整片失效 —— 排查套路与 7 类失效点

> **记录日期**: 2026-10-22
> **痛点来源**: `user_group` 一拆二（`org` + `permission_set`）后，遗留测试大面积整片挂掉
> **核心教训**: **看到"一批测试同时挂"先怀疑对象被迁移/改名，先查注册 id 与 YAML 现状，不要逐个断言去猜**

---

## 问题描述

`user_group` 拆成两个元数据对象：

| 新对象 | 表 | 含义 |
|--------|-----|------|
| `org` | `orgs` / `org_members` | 组 / 层级 / 成员 |
| `permission_set` | `permission_sets` | 权限集 |

迁移已落地：

- `v072__rename_user_groups_to_orgs.py` — 表 RENAME
- `v089__drop_legacy_user_group_and_role_tables.py` — DROP 全部 11 张 legacy 表
- `meta/schemas/user_group.yaml` — 已删除

但**按旧对象写的测试还留在仓库里**，结果不是零星失败，而是**整片失效**：

| 测试文件 | 失效形态 |
|----------|----------|
| `test_object_adaptation_user_group.py` | 21 项全挂（表名/列名/默认值/删除策略/code 约束） |
| `test_user_group_associate_audit.py` | 3 failed / 1 passed / 1 skipped |
| `test_user_group_api_extended.py` | 1 项断言误判失败 |
| `test_yaml_loader.py` / `test_display_name_service.py` | 查 `user_group` 注册 id 全部 None |
| `test_sorting_capabilities.py` | 14 项打已 sunset 的 `/api/v1/users` |

另有两个**同名陈旧副本**陷阱：仓库里早已存在 `test_object_adaptation_org.py`（旧内容，14 failed），
`git mv` 直接报 `destination exists`。

---

## 排查套路（7 步，先读事实再改代码）

```
Step 1  确认注册 id 现状    → registry.get('org') 存在？alias 还剩哪些？
Step 2  确认表名            → 读 meta/schemas/org.yaml 的 table_name
Step 3  确认字段默认值      → org_type / status / org_scope 等列是否 NOT NULL
Step 4  确认删除策略        → deletion_policy.mode = restrict 则删除断言要反转
Step 5  确认 code 约束      → pattern: ^[a-z][a-z0-9_]*$ ⇒ 测试 code 必须小写
Step 6  确认 API 状态码     → 端点是否已被 sunset（410）
Step 7  同名文件陷阱        → git mv 报 "destination exists" ⇒ 先 git rm 旧副本再 git mv
```

---

## 7 类失效点与修法

### 1. 表名改了

```python
# ❌ user_groups（v089 已 DROP）
# ✅ orgs
```

### 2. 关联表列名改了

```python
# ❌
cursor.execute('SELECT * FROM user_group_members WHERE user_id=? AND group_id=?')
# ✅
cursor.execute('SELECT * FROM org_members WHERE user_id=? AND org_id=?')
```

### 3. 必填列缺默认值

`orgs` 比 `user_groups` 多了 `org_type` / `status` / `org_scope`，
`org_members` 多了 `is_manager`。建表夹具里必须给默认值，否则 insert 直接违反 NOT NULL。

### 4. 删除策略是 restrict，不是 cascade

```python
# ❌ 断言"有子组时删除成功"
# ✅ org.yaml 的 deletion_policy.mode = restrict ⇒ 有子组时应被拒绝
result = bo_framework.delete('org', parent_id)
assert not result.success, "有子组织时应被 restrict 策略拒绝删除"
```

### 5. code 必须小写

`org.yaml` 的 `code` 有 `pattern: ^[a-z][a-z0-9_]*$` ⇒ 测试数据里的 code 一律小写。

### 6. 端点已 sunset → 410

`/api/v1/users` 自 v1.4 P8（2026-06-05）起被 `server.py` 的 `V1_CRUD_MIGRATION` 拦为 **410 Gone**。
断言必须包含 410：

```python
# ❌ assert resp.status_code in [401, 500]
# ✅
assert resp.status_code in [401, 410, 500]
```

### 7. 英文 alias 被刻意移除（最隐蔽）

`org.yaml` 的 aliases 只保留中文「用户组」，**英文 `user_group` 被刻意移除**
（注释写明：避免与 v089 DROP 后的 legacy 表混淆）：

```python
registry.get('user_group')   # → None，恒定
registry.get('org')          # → MetaObject
```

**测试里一律用注册 id（`org`），不要用英文历史名。**

---

## 铁律：临时库夹具必须自建运行时基础设施

元数据对象适配类测试直接连**临时 sqlite 库**，不经过 server 启动流程，
于是生产环境由**启动过程**建立的两样东西缺失：

| 缺失物 | 谁建立 | 缺失时报错 | 夹具补法 |
|--------|--------|-----------|----------|
| **DB config 单例** | server 启动时 `detect_runtime_config(db_path)` | `[V007.15 L0] DB config not detected yet` | 显式调 `detect_runtime_config(db_path)` |
| **`v_audit_all` 视图** | 迁移 `v007_50_add_audit_union_view.py` | `no such table: v_audit_all` | `CREATE VIEW v_audit_all AS SELECT * FROM audit_logs` |

```python
# ✅ 夹具补齐
ds = get_data_source('sqlite', database=db_path)

from meta.core.db_config_detector import detect_runtime_config
detect_runtime_config(db_path)          # ← 补 DB config 单例

ds.execute('CREATE VIEW IF NOT EXISTS v_audit_all AS SELECT * FROM audit_logs')
ds.commit()                             # ← 补审计联合视图
```

**为什么第一个坑只在写路径暴露**：`bo_framework.commit` / `rollback` 内部调 `get_runtime_config()`，
而该 module-level 单例**只在 server 初始化时被赋值**。读路径不碰它，写路径一碰就报
"config not detected yet" ⇒ **读全过、写全挂**是这类夹具的典型症状。

---

## 铁律：不要用 try/except 伪装跳过

原文件里有 15 处：

```python
# ❌ 把真失败吞掉，测试"绿"得毫无意义
try:
    result = bo_framework.create('user_group', data)
except Exception:
    pytest.fail("should not raise")
```

全部摘掉。断言要么通过，要么真失败。

---

## 结果

| 测试文件 | 结果 |
|----------|------|
| `test_object_adaptation_org.py` | 21 passed |
| `test_org_associate_audit.py` | 5 passed |
| `test_user_group_api_extended.py` | 4 passed / 8 skipped |
| `test_yaml_loader.py` | 46 passed |
| `test_display_name_service.py` | 36 passed |
| `test_sorting_capabilities.py` | 114 passed |
| `test_user_group_api.py` | 22 passed |

commit `daa53b33`（9 files, +210/-1001）。

---

## 经验总结

1. **迁移类改动的测试失效是整片的**，不是零星的。先查注册 id / YAML 现状，再动断言。
2. **英文 alias 会被刻意移除**——`registry.get('旧英文名')` 恒 None 是"设计如此"，不是 bug。
3. **删除策略先读 YAML**：`restrict` 与 `cascade` 的断言方向完全相反。
4. **端点会 sunset**：断言状态码要放行 410。
5. **临时库夹具要自建启动期基础设施**：单例（runtime config）、视图（v_*）、种子数据。
6. **不要用 try/except 伪装跳过**——失败要暴露。
7. **同名文件先 `git rm` 再 `git mv`**：仓库里可能有陈旧副本。

---

## 相关代码

- 元数据定义：[meta/schemas/org.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/org.yaml)
- 注册表别名解析：[meta/core/models.py](file:///d:/filework/excel-to-diagram/meta/core/models.py#L1349-L1359)
- DB config 单例：[meta/core/db_config_detector.py](file:///d:/filework/excel-to-diagram/meta/core/db_config_detector.py)
- 写路径依赖单例：[meta/core/bo_framework.py](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L516-L600)
- 审计视图迁移：[meta/migrations/v007_50_add_audit_union_view.py](file:///d:/filework/excel-to-diagram/meta/migrations/v007_50_add_audit_union_view.py)
- 迁移计划（重命名规划）：[docs/superpowers/plans/2026-08-28-role-to-permission-set-test-and-cleanup.md](file:///d:/filework/excel-to-diagram/docs/superpowers/plans/2026-08-28-role-to-permission-set-test-and-cleanup.md)

---

**最后更新**: 2026-10-22
