---
scene: git_message
description: Git Commit Message 格式规范 - type(scope): description [pm-authorized]
---
# Git Commit Message 规范

## 格式

```
<type>(<scope>): <description> [pm-authorized]
```

## Type 列表

| Type | 用途 | 示例 |
|------|------|------|
| `fix` | Bug 修复 | fix(import): resolve metadata validator crash on empty YAML |
| `feat` | 新功能 | feat(diagram): add zoom-to-fit button |
| `refactor` | 重构（不改行为） | refactor(annotations): simplify SemanticAnnotation init |
| `chore` | 杂务（配置/清理） | chore(gitignore): exclude runtime logs and DB backups |
| `docs` | 文档 | docs(rules): add L5 sandbox detection rule |
| `test` | 测试 | test(import): add roundtrip test for export-import |

## Scope 列表

| Scope | 覆盖目录 |
|-------|---------|
| `scripts` | scripts/ |
| `import` | meta/services/import_export_service.py |
| `gitignore` | .gitignore |
| `rules` | .trae/rules/ |
| `service_manager` | scripts/service_manager.ps1 |
| `annotations` | meta/core/models_annotations.py |
| `ui` | src/components/ |
| `api` | meta/api/ |
| `validator` | meta/core/metadata_driven_validator.py |
| `hooks` | .trae/hooks.json |
| `commands` | .trae/commands/ |

## 规则

1. **描述目的，不是内容** — "fix crash" 而非 "change line 42"
2. **不超过 72 字符** — 保持一行可读
3. **PM 授权标记** — 在主工作树 commit 时加 `[pm-authorized]`
4. **使用 `--no-verify`** — 跳过 pre-commit hooks 避免 L2 误报
5. **不要 commit 运行时产物** — logs/*.err, uploads/*.xlsx, videos/*.webm, DB backups
