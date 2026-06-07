# Spec 版本基线规范（version-baseline.md）

> **目的**：建立 spec 文档的版本基线管理（base 永久保留 + deltas 增量）模式
> **创建日期**：2026-06-06
> **维护者**：AI Agent (Trae) + Spec Author
> **关联文档**：
> - [parent_spec_refs.md](file:///d:/filework/excel-to-diagram/docs/specs/parent_spec_refs.md)
> - [spec-fr-ui-003-004-005-useMetaList-refactor.md v1.5.0](file:///d:/filework/excel-to-diagram/docs/specs/spec-fr-ui-003-004-005-useMetaList-refactor.md)
> - [spec-ui-business-logic-downflow.md v3.0.0](file:///d:/filework/excel-to-diagram/docs/specs/spec-ui-business-logic-downflow.md)

---

## 1. 为什么需要版本基线？

### 1.1 当前问题

当前 spec-fr-ui-003-004-005-useMetaList-refactor.md 演进情况：

| 版本 | 字节 | 累计增量 | 主要内容 |
|:---:|:---:|:---:|---------|
| v1.0.0 | ~50K | — | 初稿：6 service 下沉 + 接口契约 |
| v1.1.0 | ~72K | +22K | §15 头部产品对标 + 8 类 P0-P2 backlog |
| v1.2.0 | ~100K | +28K | §16-18 真实消费侧 + 组件依赖图 + v3 衔接 |
| v1.3.0 | ~125K | +25K | §19 DetailPage 双向链路 |
| v1.4.0 | ~150K | +25K | §20 ValueHelp 弹窗 5 层链路 |
| v1.5.0 | ~177K | +27K | §21-29 8 大遗漏审计 + 整体架构重构 |
| **总计** | **177K** | **+127K**（2.5x）| **累积难 review** |

**问题**：
- v1.0.0 之后内容累积**127K**，无独立 snapshot
- revert 任何版本必须 revert 整段
- diff review 只能 review 整段差异，**无法增量 review**
- 历史版本丢失，**无法回溯到任意历史版本**

### 1.2 解决方案

**base + deltas 模式**：
- **base**：v1.0.0 初稿（**永久不可变**）
- **deltas**：v1.1.0 → v1.5.0 的**5 个独立 delta 文档**
- **current_snapshot.md**：base + 5 deltas 应用后的当前内容（**自动生成**）

---

## 2. base + deltas 架构

### 2.1 目录结构

```
docs/specs/
├── parent_spec_refs.md
├── version-baseline.md              ← 本文档
│
├── useMetaList-refactor/            ← 子 spec 目录（v1.5.0 base 模式）
│   ├── spec-base-v1.0.0.md          ← 永久不可变 base
│   ├── deltas/
│   │   ├── delta-v1.1.0.md         ← v1.0.0 → v1.1.0 增量
│   │   ├── delta-v1.2.0.md         ← v1.1.0 → v1.1.0 增量
│   │   ├── delta-v1.3.0.md         ← v1.2.0 → v1.3.0 增量
│   │   ├── delta-v1.4.0.md         ← v1.3.0 → v1.4.0 增量
│   │   └── delta-v1.5.0.md         ← v1.4.0 → v1.5.0 增量
│   └── current_snapshot.md         ← 自动生成（base + 5 deltas）
│
├── spec-fr-ui-001-httpClient.md     ← 其他 11 个子 spec
├── spec-fr-ui-002-authService.md
├── ... (11 个)
│
└── spec-ui-business-logic-downflow.md v3.0.0  ← 父 spec
```

### 2.2 角色定义

| 角色 | 文件 | 状态 | 维护方式 |
|------|------|:---:|---------|
| **base** | `spec-base-v1.0.0.md` | 🔒 永久不可变 | 一次性写入，永不修改 |
| **delta** | `deltas/delta-v{N}.{M}.0.md` | 🟠 累计增加 | 每次版本升级新增一个 |
| **snapshot** | `current_snapshot.md` | 🟢 自动生成 | 由 base + 所有 deltas 合成 |

### 2.3 delta 文件格式

```markdown
# Delta v1.{N}.0：{版本标题}

> **基线版本**: v1.{N-1}.0
> **目标版本**: v1.{N}.0
> **变更日期**: {DATE}
> **变更类型**: 增量

## 1. 章节变更清单

| # | 章节 | 类型 | 摘要 |
|:-:|------|:---:|------|
| §X.Y | {标题} | 新增 | {一句话} |
| §X.Z | {标题} | 修改 | {一句话} |
| §X.W | {标题} | 删除 | {一句话} |

## 2. 详细变更

### 2.1 新增章节

#### §X.Y {标题}

[完整章节内容]

### 2.2 修改章节

#### §X.Z {标题}

**修改前**：
```diff
- {原文}
```

**修改后**：
```diff
+ {新文}
```

### 2.3 删除章节

- §X.W {标题}：删除原因
```

---

## 3. base + deltas 实施

### 3.1 历史 spec-fr-ui-003-004-005 v1.5.0 拆分

> **当前状态**：spec-fr-ui-003-004-005-useMetaList-refactor.md v1.5.0 是**单一合并文档**（177K）
> **目标状态**：拆分为 base + 5 deltas + snapshot

**实施步骤**：

| 步骤 | 任务 | 工作量 | 输出 |
|:---:|------|:-----:|------|
| 1 | 创建 useMetaList-refactor/ 目录 | 0.01d | 目录 |
| 2 | 提取 v1.0.0 章节（§0-14）作为 base | 0.1d | spec-base-v1.0.0.md |
| 3 | 提取 v1.1.0 增量（§15）作为 delta | 0.1d | deltas/delta-v1.1.0.md |
| 4 | 提取 v1.2.0 增量（§16-18）作为 delta | 0.1d | deltas/delta-v1.2.0.md |
| 5 | 提取 v1.3.0 增量（§19）作为 delta | 0.1d | deltas/delta-v1.3.0.md |
| 6 | 提取 v1.4.0 增量（§20）作为 delta | 0.1d | deltas/delta-v1.4.0.md |
| 7 | 提取 v1.5.0 增量（§21-29）作为 delta | 0.1d | deltas/delta-v1.5.0.md |
| 8 | 写脚本自动生成 current_snapshot.md | 0.1d | scripts/build_snapshot.py |
| 9 | 验证 snapshot == 原 v1.5.0 | 0.05d | 一致性测试 |
| 10 | 文档 + 维护规则 | 0.05d | 本文档 |
| **总计** | | **0.8d** | **base + 5 deltas + snapshot** |

### 3.2 未来版本（v1.6+）实施

**v1.6.0 升级流程**：

| 步骤 | 任务 | 工作量 | 输出 |
|:---:|------|:-----:|------|
| 1 | 编写 v1.6.0 新内容 | N/A | 内容 |
| 2 | 写 delta-v1.6.0.md（仅增量）| 0.2d | deltas/delta-v1.6.0.md |
| 3 | 自动重建 snapshot | 0.01d | current_snapshot.md |
| 4 | 验证 snapshot 完整性 | 0.05d | CI |
| **总计** | | **0.26d** | **每次升级 ~6h** |

### 3.3 工具脚本

```python
# scripts/build_snapshot.py（伪代码）
def build_snapshot():
    base = read('spec-base-v1.0.0.md')
    snapshot = base
    
    # 按版本号顺序应用所有 deltas
    deltas = sorted(glob('deltas/delta-v*.md'))
    for delta in deltas:
        snapshot = apply_delta(snapshot, delta)
    
    # 写入 snapshot
    write('current_snapshot.md', snapshot)
    
    # 验证（vs 原 spec）
    if file_exists('spec-fr-ui-003-004-005-useMetaList-refactor.md'):
        assert snapshot == read('spec-fr-ui-003-004-005-useMetaList-refactor.md')
```

---

## 4. 收益

### 4.1 量化收益

| 维度 | 当前（v1.5.0 合并版）| base + deltas | 收益 |
|------|-------------------|---------------|------|
| **单次 review 范围** | 177KB 整段 | 25-30KB delta | -83% |
| **revert 粒度** | 整段 | 单 delta | 灵活 |
| **回溯任意历史版本** | ❌ | ✅ 任意 delta 重新组合 | 可回溯 |
| **CI 增量验证** | ❌ | ✅ 每个 delta 独立验证 | 早发现 |
| **维护成本** | 高（每次手动合并）| 低（自动生成 snapshot）| -70% |

### 4.2 质化收益

1. **可追溯性**：每个版本升级有明确 delta 记录
2. **可逆性**：任意版本可秒回滚
3. **协作友好**：多人并发修改不同 delta 互不干扰
4. **可审计**：每次变更范围明确（base 不动 / delta 增 / snapshot 同步）
5. **可复用**：base 永久保留作为"基线参考"

---

## 5. 与其他规范的关系

### 5.1 与 parent_spec_refs.md

- **parent_spec_refs.md** = 跨 spec 引用关系
- **version-baseline.md** = 单 spec 内版本管理
- 两者互补：refs 管理 spec 间，本规范管理 spec 内

### 5.2 与 spec-fr-ui-003-004-005 v1.5.0

- **当前**：v1.5.0 合并版（177KB）作为过渡
- **目标**：base + 5 deltas + snapshot 拆分
- **时间**：见 §3.1 实施步骤（0.8d）

### 5.3 与父 spec v3.0.0

- 父 spec v3.0 同样适用 base + deltas 模式
- 但父 spec 较小（28KB），base + deltas 收益相对较低
- 建议**优先 useMetaList 子 spec 拆分**（177KB），父 spec 暂保持单文件

### 5.4 与其他 11 个子 spec

- 11 个子 spec 当前**不存在**（待编写）
- 编写时**直接采用 base + deltas 模式**（避免未来拆分）
- 模板见 parent_spec_refs.md §3.5 + 本文档 §2.3

---

## 6. 决策点（待 A2 实施时确认）

| ID | 决策项 | 推荐答案 |
|----|-------|---------|
| TBD-BASE-1 | 历史 v1.0-v1.5 拆分时机？ | 🟠 立即（基于当前 v1.5.0） |
| TBD-BASE-2 | 拆分工作是否一次性完成？ | 🟠 是（0.8d 一次性） |
| TBD-BASE-3 | 自动生成 snapshot 工具？ | ✅ 是（scripts/build_snapshot.py） |
| TBD-BASE-4 | 是否保留原 v1.5.0 单一文件？ | ✅ 是（备份 + 验证） |
| TBD-BASE-5 | 11 个新子 spec 是否采用 base + deltas？ | ✅ 是（直接采用） |
| TBD-BASE-6 | 父 spec v3.0 是否也拆分？ | 🟠 否（28KB 较小，暂不分） |

---

## 7. 维护规则

### 7.1 base 永久不可变

- 任何修改 base 的 PR **必须拒绝**
- 唯一例外：base 写错导致 spec 不可用（需明确标注 base-bug-fix）

### 7.2 delta 编号严格

- 格式：`delta-v{N}.{M}.0.md`
- 数字必须连续（v1.0.0 → v1.1.0 → v1.2.0 → ...）
- 不允许跳过或重号

### 7.3 snapshot 只能自动生成

- snapshot 禁止手动编辑
- 任何手动修改会在 CI 中失败
- 生成脚本见 §3.3

### 7.4 父 spec 不强制使用本规范

- 父 spec v3.0 暂不拆分
- 仅 useMetaList 子 spec 拆分
- 其他 11 个新子 spec 采用本规范

---

## 8. 一句话总结

> **version-baseline.md = spec 文档的"Git 化"管理：base 永久保留 + deltas 增量 + snapshot 自动生成，让任何版本可秒回滚、可增量 review、可 CI 验证。**

---

## 9. 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|:---:|------|---------|------|
| 1.0.0 | 2026-06-06 | 初稿；建立 base + deltas + snapshot 模式 | AI Agent (Trae) |
