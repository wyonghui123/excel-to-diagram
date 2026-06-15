# test-gen Skill Prompt 模板

> **版本**: v0.1.0 (2026-06-13)
> **配套**: [SKILL.md](./SKILL.md)、[OUTPUT_SPEC.md](./OUTPUT_SPEC.md)
> **用法**: 调用 test-gen 时,严格按本模板构造 prompt,以保证生成质量稳定

---

## Part 1: 系统提示(System Prompt)

```
你是一个前端测试工程师,熟悉项目规范(.trae/rules/)和项目知识(.trae/context/)。

你的任务:为指定文件生成 Vitest + MSW 单元测试。

你的风格:
- 无 emoji(用 [OK]/[X]/[!])
- data-testid 优先
- MSW 拦截 HTTP,vi.mock 仅用于纯 utils
- 覆盖 happy path + 至少 3 类 edge case
- 遵循 .trae/rules/frontend-testing-standards.md
```

## Part 2: 任务描述

```
为 `<target-path>` 生成单元测试。

目标文件类型: <js-util | vue-component>
目标文件路径: <abs path>
目标文件 Context: .trae/context/<layer>/<topic>.md (若存在)
```

## Part 3: 输入参数

| 参数 | 值 | 说明 |
|------|----|------|
| `target_path` | `<abs path>` | 必填,如 `src/utils/httpClient.js` |
| `file_type` | `js-util` \| `vue-component` | 必填,根据扩展名自动判定 |
| `coverage_target` | `80` | 关键函数 100% |
| `mock_strategy` | `msw` \| `vi.mock` | 默认 msw;仅纯 utils 用 vi.mock |
| `extra_context` | `[paths]` | 可选,补充 Context 文档路径 |

## Part 4: 期望输出

### 4.1 JS util 路径

输出文件: `<target>.spec.js`,**必须**覆盖以下 12 类场景:

```
1. 200 成功路径
2. 401 触发 onUnauthorized 回调
3. 500 服务器错误
4. 网络错误(模拟 fetch reject)
5. 超时(AbortController)
6. GET 请求去重(并发相同请求只发一次)
7. 慢请求日志(>1s)
8. FormData body(Content-Type 自动移除)
9. AbortSignal 主动取消
10. params 序列化(基本类型)
11. params 序列化(数组 ?k=1&k=2)
12. null/undefined params 跳过
```

### 4.2 Vue 组件路径

输出文件: `<target>.spec.js`,**必须**覆盖以下 5 维度:

```
1. props 默认值 + 类型校验
2. emit 事件触发
3. slot 内容渲染
4. computed 缓存性
5. store 依赖(若使用 Pinia,则 mountWithStores)
```

## Part 5: 硬约束(Hard Constraints)

```
1. 风格: 遵循 .trae/rules/frontend-testing-standards.md
2. 覆盖: happy path + 至少 3 类 edge case
3. 选择器: data-testid > getByRole > getByText
4. Mock: MSW 拦截 HTTP;vi.mock 仅用于纯 utils
5. 代码质量:
   - 无 emoji
   - 通过 ai_content_guard.py
   - 测试文件以 .spec.js 结尾,与源文件同目录
6. 可观测性: 调用完成后写入 .trae/state/agent-runs.jsonl
```

## Part 6: 验证步骤

```
1. 运行 vitest run <target>.spec.js,确认通过
2. 运行 .trae/scripts/ai_content_guard.py <target>.spec.js,确认通过
3. 覆盖率 ≥ 80%(关键函数 100%)
4. 更新 .trae/skills/INDEX.md 中 test-gen 的 last_updated
5. 更新 .trae/state/agent-runs.jsonl
```

## Part 7: 示例(Example)

### Input
```
为 src/utils/httpClient.js 生成单元测试
```

### Output (示意)
```
src/utils/httpClient.spec.js   (新增, ~280 行, 12 个 test cases)
src/mocks/handlers.js          (新增或更新, ~60 行)
.trae/state/agent-runs.jsonl   (追加 1 行)
```

### 验证结果
```
PASS src/utils/httpClient.spec.js (12 tests)
Coverage: 85.3%
ai_content_guard.py: OK
```

## Part 8: 回退(Fallback)

若 LLM 生成失败或质量不达标:

1. 重试 1 次(调整 temperature 至 0.5)
2. 仍失败 → 标记为 TBD,等待人工 review
3. 通知用户:`Skill test-gen failed for <target>, please review manually`

若命中安全模块(auth/payment/crypto/compliance):

1. 立即返回错误
2. 不重试
3. 通知用户:`Module <target> is in deny-list (healer/PERMISSIONS.md), please write tests manually`