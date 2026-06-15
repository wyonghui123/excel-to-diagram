# Skill 编写规范

> **版本**: v1.0 (2026-06-13)
> **目的**: 约束本项目 `.trae/skills/` 下的所有 Skill 文件编写流程,保证一致性、可发现性、可维护性。

## 1. 适用范围

本文档适用于 `.trae/skills/<skill-name>/SKILL.md` 所有 Skill 的编写、修改、删除。

不适用于:
- `.trae/rules/`(规则,非 Skill)
- `.trae/context/`(知识,非 Skill)
- `.trae/skills/_TEMPLATE/`(模板,只读)

## 2. Skill 文件命名与目录结构

```
.trae/skills/
├── _TEMPLATE/                    # [只读] 模板,正式 Skill 不要放这里
│   ├── SKILL.md
│   └── PROMPT_TEMPLATE.md
├── <skill-name>/                # 正式 Skill
│   ├── SKILL.md                  # 必须
│   ├── PROMPT_TEMPLATE.md        # 推荐
│   └── OUTPUT_SPEC.md            # 可选
├── healer/
│   └── PERMISSIONS.md           # 特殊:Healer 边界
├── INDEX.md                      # 注册表(必填)
├── SCHEDULING.md                 # 调度规则(必填)
├── SKILL_AUTHORING.md            # 本文档
└── CHANGELOG.md                  # 变更日志(必填)
```

## 3. SKILL.md frontmatter 规范

### 3.1 必填字段

| 字段 | 类型 | 约束 |
|------|------|------|
| `name` | string | 全小写、连字符分隔;与目录名一致 |
| `description` | string | **必须含"做什么"+"何时调用"**,建议 < 200 字符 |
| `version` | semver | 初始 0.1.0;每次更新递增 |
| `last_updated` | ISO8601 | 格式 `YYYY-MM-DD` |

### 3.2 推荐字段

| 字段 | 类型 | 用途 |
|------|------|------|
| `triggers` | string[] | 触发短语列表(供 Agent 匹配) |
| `inputs` | glob[] | 输入文件模式 |
| `outputs` | glob[] | 输出文件模式 |
| `tools` | string[] | 依赖工具(filesystem/git/mcp server) |
| `author` | enum | `human` 或 `AI` |

### 3.3 description 编写规范

**错误示例**(过短 / 无触发):
```yaml
description: "生成测试代码"
```

**错误示例**(过长):
```yaml
description: "本 Skill 用于在前端项目中根据用户输入的目标文件路径、上下文文档、既有测试模式,使用 Vitest + MSW + happy-dom + @vue/test-utils 工具链,为 JS 函数或 Vue 组件生成符合 .trae/rules/frontend-testing-standards.md 规范的单元测试,覆盖 happy path + 3 类 edge case..."
```

**正确示例**:
```yaml
description: "Generate Vitest + MSW unit tests for JS utils and Vue components. Invoke when user asks to write tests, add test coverage, or generate test file for an existing module."
```

## 4. SKILL.md 正文 7 节规范

正文必须包含以下 7 节(顺序可调整,内容不可缺):

| 节 | 必填 | 说明 |
|----|------|------|
| 1. 触发条件 | [OK] | 何时激活、何时**不**激活 |
| 2. 必读上下文 | [OK] | Agent 必须先读的文件清单 |
| 3. Prompt 模板引用 | [OK] | 指向 PROMPT_TEMPLATE.md |
| 4. 硬约束 | [OK] | 不可违反的清单(checkboxes 形式) |
| 5. 输出规范 | [OK] | 输出文件路径、格式 |
| 6. Failure Mode | [OK] | 失败时的降级、回退策略 |
| 7. Observability Hook | [OK] | 如何被 `_metrics` 采集 |

## 5. 硬约束清单标准

每个 Skill 的"硬约束"必须包含以下 7 项(可扩展):

- [ ] 不使用 emoji
- [ ] data-testid 优先
- [ ] MSW mock 而非模块 mock
- [ ] 覆盖 happy path + 至少 3 类 edge case
- [ ] 通过 `.trae/scripts/ai_content_guard.py` 检查
- [ ] 不修改既有 `.trae/rules/` 文件
- [ ] 跨 Agent 并行时通过 git lock 串行化写操作

## 6. 注册与变更流程

### 6.1 新增 Skill

1. 复制 `_TEMPLATE/SKILL.md` 到 `<skill-name>/SKILL.md`
2. 填写所有 `<占位符>`
3. 在 `.trae/skills/INDEX.md` 注册(append)
4. 在 `.trae/skills/CHANGELOG.md` 追加记录
5. 更新 `<skill-name>/SKILL.md` 的 `last_updated`

### 6.2 修改 Skill

1. 修改 SKILL.md 或 PROMPT_TEMPLATE.md
2. 递增 version(breaking → major, feature → minor, fix → patch)
3. 更新 last_updated
4. 在 CHANGELOG.md 追加 entry
5. 若为 AI 修改,在 `author` 字段标注 `AI`(或追加 `author_history`)

### 6.3 删除 Skill

1. 在 CHANGELOG.md 标注 deprecated + 替代 Skill
2. 等待 7 天观察期
3. 删除目录
4. 在 INDEX.md 删除条目

## 7. 质量门禁(PR Review Checklist)

提交 PR 时,reviewer 验证:
- [ ] frontmatter 字段完整
- [ ] description 长度 < 200 字符
- [ ] 正文含 7 节
- [ ] 硬约束清单 ≥ 7 项
- [ ] INDEX.md 已更新
- [ ] CHANGELOG.md 已追加
- [ ] 通过 `ai_content_guard.py`
- [ ] 多 Agent 隔离策略已说明

## 8. 工具兼容性

- **aiwg 2026.5.13+**: 直接转换至 Claude Code、Cursor、Copilot、Warp、OpenClaw
- **Cursor**: 自动识别 frontmatter 转为 `.cursor/rules/*.mdc`
- **Claude Code**: 识别 frontmatter 中的 name/description
- **其他**: 通用 markdown,可被任何工具读取

## 9. 反模式(Anti-Patterns)

- [X] Skill 内含 emoji(`⛔` `✅` `❌`)
- [X] description 仅说"做什么"不说"何时调用"
- [X] 硬约束未写明,只说"按 best practice"
- [X] 修改既有 `.trae/rules/` 文件
- [X] SKILL.md 与 PROMPT_TEMPLATE.md 内容重复
- [X] author 字段缺失或乱填
- [X] last_updated 是未来日期

## 10. 参考

- `.trae/skills/_TEMPLATE/SKILL.md`(模板)
- `.trae/skills/_TEMPLATE/PROMPT_TEMPLATE.md`(Prompt 模板)
- `.trae/skills/INDEX.md`(注册表)
- `.trae/rules/SESSION_REMINDER.md`(全局规则)
- 业界: [aiwg 2026.5.13](https://pypi.org/project/aiwg/) 跨平台 Skill 同步