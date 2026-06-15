# <Skill Name> Prompt Template

> **本文件为 Prompt 模板,使用前请复制并按需修改占位符。**
> **注意**:Skill 调用方必须严格按此模板构造 prompt,以保证生成质量稳定。

## System Context(系统上下文)

你是一个 `<role>`(如:测试工程师 / 前端架构师 / DevOps)。

你熟悉以下项目规范:
- `.trae/rules/`(项目规则)
- `.trae/context/`(项目知识图谱)
- `.trae/skills/`(可用 Skill 列表)
- 本 Skill 的 `SKILL.md`(执行规范)

## Task(任务描述)

<用户原始请求,保留原话>

## Inputs(输入)

| 类型 | 路径 / 值 |
|------|----------|
| 目标文件 | `<abs path>` |
| 上下文 | `.trae/context/<file>.md` |
| 既有测试 | `<path>`(若存在) |

## Expected Output(期望输出)

<具体描述输出文件的格式、内容、覆盖范围>

## Hard Constraints(硬约束)

1. **风格**: 遵循 `<reference-style-file>`(如 `frontend-testing-standards.md`)
2. **覆盖**: happy path + 至少 3 类 edge case(空值/边界/错误)
3. **选择器**: 优先 `data-testid`,次之 `getByRole`
4. **Mock**: MSW 拦截 HTTP,`vi.mock` 仅用于纯 utils
5. **代码质量**:
   - 无 emoji
   - 通过 `ai_content_guard.py`
   - 测试文件以 `.spec.js` 结尾
6. **可观测性**: 调用完成后写入 `agent-runs.jsonl`

## Verification(验证步骤)

1. 运行 `<test command>`,确认通过
2. 运行 `<lint command>`,确认无警告
3. 运行 `.trae/scripts/ai_content_guard.py <output-file>`,确认通过
4. 更新 `.trae/skills/INDEX.md` 中本 Skill 的 `last_updated`

## Example(示例)

### Input
```
为 src/utils/httpClient.js 生成单元测试
```

### Output
```
src/utils/httpClient.spec.js  (新增, ~250 行)
src/mocks/handlers.js         (新增或更新, ~50 行)
.trae/state/agent-runs.jsonl  (追加 1 行)
```

### 验证结果
```
PASS src/utils/httpClient.spec.js (12 tests)
ai_content_guard.py: OK
```

## Fallback(回退)

若 LLM 生成失败或质量不达标:
1. 重试一次(调整 temperature)
2. 仍失败 → 标记为 TBD,等待人工 review
3. 通知用户:`Skill <name> failed, please review manually`