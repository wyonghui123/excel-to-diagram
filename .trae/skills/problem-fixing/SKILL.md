---
name: problem-fixing
description: pytest测试问题修复工作流。包含fix_tasks.json任务管理、认领、修复、验证。当智能体需要修复--failed或--skip产生的测试问题时调用。
---

# 测试问题修复工作流

> 本 Skill 管理 `fix_tasks.json` 中的修复任务（多会话并行协同）

## 一、核心原则

- `fix_tasks.json` 是唯一任务状态来源
- 所有智能体会话读写同一个文件，自动协同
- 三种任务类型：T（failed/error）、S（skipped）

## 二、任务类型速查

| 类型 | ID 前缀 | 来源 | 验证命令 |
|------|---------|------|----------|
| failed | T | `--failed` 确认 | `python d:\filework\test.py --failed` |
| error | T (ERROR_前缀) | `--failed` 确认 | `python d:\filework\test.py --failed` |
| skipped | S | `import-skip` | `python d:\filework\test.py --skip` |

## 三、修复工作流

### 3.1 查看任务状态

```bash
python d:\filework\fix_task_manager.py status    # 所有任务
python d:\filework\fix_task_manager.py next      # 推荐任务
```

### 3.2 认领任务（避免多会话冲突）

```bash
python d:\filework\fix_task_manager.py claim S001           # S 前缀用 skip ID
python d:\filework\fix_task_manager.py claim <category名>   # T 前缀用分类名
```

### 3.3 修复 → 验证 → 完成

```bash
# ... 编写修复代码 ...

# 验证修复
python d:\filework\test.py --failed   # 验证 T 任务 (failed/error)
python d:\filework\test.py --skip     # 验证 S 任务 (skipped)

# 更新进度
python d:\filework\fix_task_manager.py progress T002 10

# 完成任务（自动验证门禁）
python d:\filework\fix_task_manager.py complete S001
# 验证失败会阻断并显示 HINT，需修复后重试
```

### 3.4 Skip 任务完整工作流

```bash
# Step 1: 分析生成任务
python d:\filework\skip_analyzer.py

# Step 2: 导入任务
python d:\filework\fix_task_manager.py import-skip

# Step 3: 认领 → 修复 → 完成
python d:\filework\fix_task_manager.py claim S001
# ... 修复代码 ...
python d:\filework\fix_task_manager.py complete S001   # 自动验证

# 仅限 analyze/keep 任务：跳过验证
python d:\filework\fix_task_manager.py complete S001 --force

# 审计 + 正规改 action
python d:\filework\fix_task_manager.py audit
python d:\filework\fix_task_manager.py reclassify S001 keep --reason "..."
```

## 四、自动同步机制

| 触发条件 | 行为 |
|---------|------|
| `--failed` 运行完毕 | sync 从 confirmed_issues 自动生成 T 任务 |
| `--skip` 全部通过 (0F+0E+0S) | 自动完成 S 任务 |
| `--failed` all_passed | 自动完成所有 T 任务 |

## 五、状态机

```
idle → --all → passed (全部通过)
idle → --all → needs_rerun (有失败)
                  ↓
             --failed → passed (修复成功)
             --failed → fixing (仍有错误)
                          ↓
                       修复 → --failed → ...
```

## 六、铁律

- **禁止直接运行 `pytest`** — 唯一入口：`python d:\filework\test.py`
- `--all` 后必须跑 `--failed` 确认（`--all` 并行会有假失败）
- 修复后跑 `--failed` 而非 `--all`（节省时间）
- 两个智能体不要同时认领同一任务（用 claim 避免）
