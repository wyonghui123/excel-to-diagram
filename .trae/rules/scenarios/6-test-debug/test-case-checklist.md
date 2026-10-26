---
alwaysApply: false
description: "测试用例反模式 + 检查清单 + 快速诊断"
globs: "meta/tests/**/*,tests/**/*"
---

# 测试用例检查清单

> **拆分自** `test-case-standards.md` v1.1
> **本文件覆盖**：§9 反模式 + §10 检查清单 + 附录 A/B
> **其他章节**：[test-case-design.md](./test-case-design.md)（§1-4）/ [test-case-runtime.md](./test-case-runtime.md)（§5-7）/ [test-case-excel.md](./test-case-excel.md)（§8）

---

## 9. 反模式清单

以下是本次测试修复中发现的**具体反模式**，新增测试时必须避免：

| # | 反模式 | 后果 | 修复方式 |
|---|--------|------|---------|
| 1 | `autouse` fixture teardown 不恢复状态 | 后续测试大面积失败 | 保存原始状态并恢复 |
| 2 | 缓存层不感知底层状态变化 | 返回失效数据 | 读取缓存前验证数据源 |
| 3 | session-scope client 不清理 cookie | 认证状态泄露 | 每次使用前 `_cookies.clear()` |
| 4 | 修改 `registry._objects` 不清除缓存 | 缓存与实际状态不一致 | 同步清除缓存或验证 |
| 5 | `setup_class` 中硬编码 `TESTING` 设置 | 非测试环境风险 | 使用 `get_shared_app()` 统一管理 |
| 6 | 测试间共享可变全局变量 | 测试顺序依赖 | 每个 test class 独立初始化 |
| 7 | `teardown` 中不清理创建的数据 | 数据累积，测试冲突 | 追踪并清理所有创建的资源 |
| 8 | 依赖 `--all` 的并行执行顺序 | 结果不稳定 | 确保串行和并行都通过 |
| 9 | 只验证 API 状态码，不验证 Excel 文件内容 | "假通过"：样式/验证/注释错误未被发现 | 用 openpyxl 回读验证 |
| 10 | API 响应链式 `.get()` 不加 isinstance 检查 | `AttributeError: 'list' object has no attribute 'get'` | 每层 `.get()` 前检查类型 |
| 11 | 硬编码 openpyxl 颜色值（如 `"#E0E0E0"`） | 断言永远失败（openpyxl 返回 8 位 `"00E0E0E0"`） | 用 `endswith()` 或引用 `ExcelDesignSystem` 常量 |
| 12 | 测试间共享同一个 Workbook 对象 | 写入操作互相污染 | 每个测试创建独立 Workbook |
| 13 | 临时 Excel 文件不清理 | 磁盘空间泄漏 | 使用 `tmp_path` 或 `try/finally + os.unlink` |
| 14 | 用 `try/except: pytest.fail` 伪装跳过 | 真失败被吞，测试"绿"得毫无意义 | 摘掉伪装，断言要么通过要么真失败 |
| 15 | 断言写死旧对象名（如 `user_group`） | 对象迁移后 `registry.get()` 返回 None，全挂 | 先确认注册 id 现状，再改断言 |
| 16 | 沿用旧英文 alias | 迁移后 alias 被刻意移除，`registry.get('旧名')` 恒 None | 用**注册 id**（`org`），不用英文历史名 |
| 17 | 端点已 sunset 仍断言 401/500 | 实际返回 410，断言误判为失败 | 允许 410：`assert status in [401, 410, 500]` |
| 18 | 断言删除"成功" | `deletion_policy.mode: restrict` 时实际拒绝删除 | 先读 YAML 的 deletion_policy 再定断言方向 |

---

## 9.1 元数据对象迁移后的测试清理套路（2026-10-22 实例）

> **背景**：`user_group` 一拆二 → `org`（组）+ `permission_set`（权限集）。
> 表已 RENAME（v072）、legacy 表已 DROP（v089）、`user_group.yaml` 已删。
> 结果：按旧对象写的测试**大面积整片失效**，不是零星失败。

**排查顺序（先读事实，再改代码）**：

```
Step 1  确认注册 id 现状    → registry.get('org') 是否存在？alias 还剩哪些？
Step 2  确认表名            → 读 meta/schemas/org.yaml 的 table_name
Step 3  确认字段默认值      → org_type / status / org_scope 等列是否 NOT NULL
Step 4  确认删除策略        → deletion_policy.mode = restrict 则删除断言要反转
Step 5  确认 code 约束      → pattern: ^[a-z][a-z0-9_]*$ ⇒ 测试 code 必须小写
Step 6  确认 API 状态码     → 端点是否已被 sunset（410）
Step 7  同名文件陷阱        → git mv 报 "destination exists" ⇒ 仓库里早有陈旧副本
                            → 先 git rm 旧副本，再 git mv 迁移版归位
```

**实测产出**（5 个测试文件）：21 + 5 + 4 + 46 + 36 + 114 项全绿，
覆盖「表名/列名/默认值/删除策略/code 约束/410 端点/别名移除」7 类失效点。

> **教训**：迁移类改动留下的测试失效是**整片**的，不是零星的。
> 看到「一批测试同时挂」先怀疑对象被迁移/改名，**先查注册 id 与 YAML 现状**，
> 不要逐个断言去猜。

---

## 10. 检查清单

### 新增测试时

- [ ] 测试能独立运行吗？（`python -m pytest <test> -xvs -n0`）
- [ ] 与同文件其他测试无顺序依赖？（随机顺序运行验证）
- [ ] 与项目其他测试文件无污染？（随机组合验证）
- [ ] 创建的数据在 teardown 中清理了吗？
- [ ] 修改的全局状态在 teardown 中恢复了吗？
- [ ] 使用了唯一标识符吗？（非硬编码 ID/name）
- [ ] 依赖 session-scope fixture 时考虑了状态污染吗？
- [ ] **涉及 Excel 导入导出？→ 是否用 openpyxl 验证了文件内容？**
- [ ] **API 响应解析是否加了 isinstance 防御？**

### 修改现有测试时

- [ ] 修改前运行了 `--all --force` 建立基线吗？
- [ ] 修改后运行了 `--failed` 确认修复了吗？
- [ ] 确认修复没有引入新的污染吗？（`--all --force` 最终验证）
- [ ] 更新了 `test_confirmed_issues.json` 中的问题状态吗？

### 排查测试失败时

- [ ] 单独运行这个测试能通过吗？
- [ ] 与其他失败测试一起运行能通过吗？
- [ ] 失败的测试有什么共同的 fixture 依赖？
- [ ] 是否有 autouse fixture 可能泄漏状态？
- [ ] 是否有 session-scope fixture 可能累积状态？
- [ ] **`AttributeError: 'list' object has no attribute 'get'`？→ 检查 API 响应 isinstance 防御**

---

## 附录 A：本次修复记录

| 日期 | 问题 | 文件 | 修复 | 类型 |
|------|------|------|------|------|
| 2026-05-31 | Cookie 泄露 | `conftest.py` | `get_shared_app()` 中添加 `_cookies.clear()` | 状态隔离 |
| 2026-05-31 | Registry 清空不恢复 | `test_hierarchy_bo.py` | `clean_registry` fixture 保存/恢复 `_objects` | 状态恢复 |
| 2026-05-31 | 缓存与状态不一致 | `yaml_loader.py` | 缓存返回前检查 `registry._objects` 非空 | 缓存安全 |
| 2026-05-31 | 测试顺序污染 | 多个文件 | 识别为基础设施问题，非代码缺陷 | 诊断方法 |
| 2026-10-22 | user_group→org 迁移后测试整片失效 | `test_object_adaptation_org.py` 等 5 个文件 | 表名/列名/默认值/删除策略/code 约束/410 端点/别名移除 7 类修正 | 迁移清理 |

## 附录 B：快速诊断命令

```bash
# 确认真实错误（排除并发假失败）
python d:\filework\test.py --all --force    # 全量并行基线
python d:\filework\test.py --failed         # 串行确认（地面真相）

# 验证测试独立性
python -m pytest <file1> <file2> -xvs -n0   # 跨文件组合测试

# 查看当前问题状态
python d:\filework\test.py --status

# 查看结构化问题详情
python -c "import json; d=json.load(open('d:/filework/test_confirmed_issues.json')); \
  [print(f'{i[\"test\"]}: {i.get(\"error_message\",\"\")[:100]}') for i in d.get('confirmed_failed',[])]"
```

---

## CHANGELOG

| 日期 | 变更 | 内容 |
|---|---|---|
| 2026-10-22 | v1.2 | **补反模式 14–18 + §9.1 元数据对象迁移后的测试清理套路**（user_group→org 实例） |
| 2026-09-02 | 拆分 | 从 test-case-standards.md §9-10 + 附录 拆出 |