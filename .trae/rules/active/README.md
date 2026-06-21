# Active Rules (当前生效规则)

> **唯一权威入口** - AI Agent 应读取此目录下的规则，不是根目录。

## 目录用途

| 目录 | 用途 | 维护者 |
|------|------|--------|
| `../active/` (本目录) | 当前生效的规则 | PM 审查后放入 |
| `../archive/` | 历史版本（只读，不可修改）| 自动迁移 |
| `../` (根目录) | **向后兼容层** - 软链/复制到 active/ | 保持不变以兼容旧引用 |

## 规则版本管理流程

### 1. 新增/修改规则

```
1. 编辑 active/<新规则名>.md
2. 更新 active/CHANGELOG.md
3. 同时复制到 ../ (根目录) 保持向后兼容
4. 如果是弃用旧版本，移动到 archive/
```

### 2. 弃用规则

```
1. 把规则从 active/ 移动到 archive/
2. 在 archive/<rule>.md 顶部加 [DEPRECATED] 标记
3. 更新 active/CHANGELOG.md 和 active/README.md
```

### 3. 版本号约定

格式：`v<YYYYMMDD>-<major>`

示例：
- `multi-agent-infrastructure-v20260620-v1.md` (2026-06-20 V1)
- `multi-agent-infrastructure-v20260620-v2.md` (2026-06-20 V2)
- `multi-agent-infrastructure-v20260621-v2.1.md` (2026-06-21 V2.1)

## 迁移状态 (2026-06-21)

| 规则 | 当前状态 | 迁移位置 |
|------|---------|---------|
| SESSION_REMINDER.md v3 | active + root (双份) | 待迁移 |
| multi-agent-infrastructure-v20260620-v2.md (V2.1) | active + root (双份) | 待迁移 |
| multi-agent-infrastructure-v20260620.md (V1) | root only | **移到 archive** |
| 其他 30+ 规则 | root only | 评估中 |

## 为什么需要 active/archive？

### 问题 (V2.1 之前)

- 规则演进混乱：不知道哪个是权威版本
- 引用关系不清楚：multi-agent-coordination.md 引用 V1，但 V2.1 已存在
- 旧规则无法删除：怕破坏现有引用
- 多个版本并存：V1 + V2 + V2.1 同时生效

### 解决

- `active/` = 唯一权威 (PM 审查)
- `archive/` = 历史快照 (只读)
- 根目录 = 向后兼容 (软链/复制)
- CHANGELOG = 演进历史 (完整可追溯)

## 自动化脚本

- `scripts/check_active_rules.py` (待实施) - 检测规则是否同时存在于 active/ 和 root/
- `scripts/migrate_to_active.py` (待实施) - 批量迁移规则到 active/

## 相关 V2.1 铁律

- **铁律 12**: 修复完整性自动检查 (脚本: `scripts/check_fix_completeness.py`)
- **铁律 13**: 决策日志强制 (脚本: `scripts/decision_log.py`)

---

_本目录由 V2.1 元反馈建立（2026-06-21）_
_参考：`.trae/rules/multi-agent-infrastructure-v20260620-v2.md` § 7.6_