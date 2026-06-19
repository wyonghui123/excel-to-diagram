# T-fix-edit-tab-watch-iterable

> **Task ID**: T-fix-edit-tab-watch-iterable
> **Agent**: agent-edit-tab-fix
> **基于 commit**: 8b6204b (fix-edit-tab-state-2026-06-18)
> **风险等级**: 🟢 low (一行解构顺序调整，纯 bug fix)
> **开始时间**: 2026-06-18

---

## 1. 任务描述

修复 [DetailPage.vue:818](file:///d:/filework/agent-edit-tab-fix/src/components/common/DetailPage/DetailPage.vue#L945) watch immediate 时的运行时报错：

```
TypeError: undefined is not iterable (cannot read property Symbol(Symbol.iterator))
    at watch.immediate
```

---

## 2. 改动文件白名单 ✅

```yaml
modified_files:
  - src/components/common/DetailPage/DetailPage.vue

new_files: []
deleted_files: []
```

---

## 3. 禁止改文件黑名单 🚫

```yaml
forbidden_files:
  - .agent-status.json
  - service_manager.ps1
  - scripts/agent_bootstrap.ps1
  - .git/hooks/pre-commit
  - healthy-baseline-2026-06-17
  - multi-agent-coordination.md
```

---

## 4. 依赖关系

```yaml
depends_on:
  - commit: 8b6204b  # 上一个 commit 引入了这个 bug

blocks: []
```

---

## 5. 完成标准 ✅

```yaml
acceptance_criteria:
  - [x] 改动只在白名单内
  - [x] 没有改动黑名单文件
  - [x] watch callback 不再解构 undefined
  - [x] 首次执行保留 isFirstRun 语义
  - [x] "切走 tab 状态/切回不重置 internalEditing" 行为保留
  - [x] 没有引入新代码风格问题
```

---

## 6. 风险评估

### 6.1 改动范围

| 维度 | 评估 |
|------|------|
| **文件数量** | 1 |
| **新增行数** | +10 (含注释) |
| **删除行数** | -7 |
| **影响模块** | DetailPage watch 逻辑 |

### 6.2 风险等级

```yaml
risk_level: low

reason: |
  纯 bug fix：上一 commit 的 watch 用了 [oldObjectType, ...] = oldVal
  立即解构，但 Vue 3 watch immediate 时 oldVal=undefined 导致运行时报错。
  修复方法：把 newVal/oldVal 作为标量参数接收，进入 callback 后再解构。
```

### 6.3 缓解措施

```yaml
mitigation:
  - 回滚方案: git revert 即可一行回退
  - 测试覆盖: 浏览器手动测试 "编辑态 → 切 app tab → 切回" 流程
  - 监控指标: console 是否有 [DetailPage] watch (first run) 正常输出
```

---

## 9. 工作日志

```yaml
decisions:
  - 2026-06-18 17:00: 决定修复方案为标量接参+内部解构而非强制初始化 oldVal，
    因为前者更符合 Vue 3 watch 习惯用法且对其他分支影响最小。

insights:
  - Vue 3 watch immediate 时 oldVal 是 undefined（不是数组初值），
    这是常见踩坑点，所有用数组作为 source 的 watch 都要注意。
```

---

> **铁律**:
> L1-Worktree: yes
> L2-NoMain: yes
> L3-Stash: yes
> L4-Status: yes
> L5-Service: yes
