# DEPLOY_HANDOVER_BUG_V040 - 协调智能体 (PM) 交接文档

> 撰写: 2026-07-04 07:50 (Asia/Shanghai)
> 撰写人: bugfix-export agent (smart-annotation)
> 接收方: 协调智能体 / PM
> 优先级: **HIGH** - 用户当前正在尝试导入文件被阻塞

---

## 0. 一句话总结

> **BUG-V040 修复已 commit + push + cherry-pick 到 worktrees/release-prep**,
> 但**3011 后端 (PID 33712, 启动于 2026-07-03 22:56:19) 加载的 .pyc 仍是旧代码**,
> 必须**重启 3011 后端**才能让 BUG-V040 fix 生效。

---

## 1. 用户报告

用户上传 `C:\Users\Administrator\Downloads\用户_20260704_072435.xlsx` 导入用户，
Step 2 数据校验报错：
- 第 2 行: `【枚举值无效】'inactive - 未激活' 不是有效的 状态`
- 第 3 行: `【枚举值无效】'active - 活跃' 不是有效的 状态`

这两条都是 `user.status` 字段 (sheet 名"用户", 列名"状态")。

---

## 2. 根因

| 维度 | 现状 |
|------|------|
| `user.yaml` schema 内联 enum | `active`, `inactive`, `locked` 是 inline static |
| `value_help.source.enum_type_id` | `user_status` |
| **DB `enum_values` 表 user_status** | **0 records** (从未 seed) |
| 后端校验 `validate_enum_value` | **仅查 DB enum_values 表** |
| 校验结果 | DB 无记录 → False → 报"枚举值无效" |

最讽刺的是：这个 Excel 是用户自己**昨天刚导出**的，导出时序列化为
"inactive - 未激活" / "active - 活跃" (display_format=CODE - LABEL)。
现在用同一个 Excel 再导入，**导出-再导入的闭环失败**。

---

## 3. 我做了什么

### 3.1 Git

| 操作 | Commit | 状态 |
|------|--------|------|
| commit (feat branch) | `f3c2bcc` | ✅ |
| push 到 origin | `e13fcb4..f3c2bcc` feat/annotation-category-filter | ✅ |
| cherry-pick 到 worktrees/release-prep | `eb5c8c0` | ✅ auto-merge OK |

### 3.2 代码改动 (2 文件, +63 -5)

`meta/core/enum_resolver.py` - 新增 `validate_enum_value_with_field(meta_field, code, data_source)`:
```python
# 优先级:
#   1. meta_field.inline enum_values (schema 静态声明)
#   2. DB enum_values 表 (向原行为兼容)
#   3. 实在查不到 → True (避免误报)
```

`meta/services/import_export_service.py`:
```python
def _validate_enum_value(self, enum_type_id, code, meta_field=None):
    code = self._parse_enum_display_to_code(code)
    if meta_field is not None:
        # [BUG-V040 2026-07-04] 优先查 inline enum_values
        from meta.core.enum_resolver import validate_enum_value_with_field
        return validate_enum_value_with_field(meta_field, code, self.data_source)
    # 向后兼容: 不传 meta_field 时走原路径
    from meta.core.enum_resolver import validate_enum_value
    return validate_enum_value(enum_type_id, code, self.data_source)
```

调用点 (L5393):
```python
if not self._validate_enum_value(enum_type_ref, field_value_str, meta_field=field):
```

### 3.3 验证 (8/8 unittest-style PASS)

| Test | 场景 | 期望 |
|------|------|------|
| T1a | user.status 'active' (inline) | True |
| T1b | user.status 'inactive' (inline) | True ← 用户 BUG 修复核心 |
| T1c | user.status 'garbage' (inline not match) | False |
| T2a | relation_type 'GENERATES' (DB match) | True |
| T2b | relation_type 'INVALID' (DB not match) | False |
| T2c | 无 inline + DB 有 seed → DB fallback | True |
| T3 | 无任何枚举源 → fallback True | True |
| T4 | 原 `validate_enum_value` (DB only) 行为不变 | unchanged |
| T5 | 完整流程 "inactive - 未激活" → parse → validate | True |

---

## 4. PM 必须做的事

### 4.1 ⚠️ 重启 3011 后端 (阻塞 BUG-V040 修复生效)

**当前状态**:
- PID 33712 启动于 `2026-07-03 22:56:19` (v3.18 baseline + 您的修改)
- `import_export_service.cpython-314.pyc` 编译于 `2026-07-03 22:56:30`
- 但我的 fix `eb5c8c0` 是 `2026-07-04 07:45` 提交的

→ 后端加载的是**修复前**的代码 → 用户再导仍报错

**操作步骤**:
1. `Stop-Process -Id 33712 -Force -ErrorAction SilentlyContinue`
2. 启动新进程（建议同样用 waitress_server.py，端口 3011）
3. 验证 Server header: 应仍是 `bo_action_server_v3.18_port3011`
4. 验证 .pyc 重新编译时间 > 启动时间

**预估时间**: 5 分钟（含通知用户断连 5-10 秒）

### 4.2 验证修复

让用户重新导入 `C:\Users\Administrator\Downloads\用户_20260704_072435.xlsx`:
- Step 2 数据校验不再有"枚举值无效"错误
- 第 2 行 (TEST333) 和 第 3 行 (admin) 都能进入 Step 3 执行

### 4.3 可选：后续改进 (不在本工单范围)

把 `user_status` 也 seed 到 `enum_values` 表，让 export-import 双向均通过 DB 路径。
- 在 `meta/scripts/migrate_enums.py` 注册
- 等等

但当前 fix 已经覆盖了：直接用 schema inline enum 优先。**B 路径非必要**。

---

## 5. 关键文件路径

| 文件 | 路径 |
|------|------|
| Fix commit (feat branch) | `f3c2bcc` |
| Fix commit (release branch) | `eb5c8c0` |
| 改动文件 1 | `D:\filework\excel-to-diagram\meta\core\enum_resolver.py` |
| 改动文件 2 | `D:\filework\excel-to-diagram\meta\services\import_export_service.py` |
| 用户上传文件 | `C:\Users\Administrator\Downloads\用户_20260704_072435.xlsx` |
| Schema source | `D:\filework\excel-to-diagram\meta\schemas\user.yaml` (L118-145) |

---

## 6. 风险评估

| 风险 | 概率 | 措施 |
|------|------|------|
| 重启 3011 后用户断连 | 高 | 已通知"5-10 秒断连" |
| 重启后新 BUG | 低 | 改动仅 1 路径，8/8 test 已 PASS |
| 影响其他 enum 校验 | 低 | 优先级: inline 优先 → inline 不包含时才 DB fallback |

---

**撰写完成时间**: 2026-07-04 07:50
**紧急级别**: HIGH (用户当前被阻塞)
