# 测试规则权威索引 (v1.0)

> **Date**: 2026-06-15 | **Status**: 提案 (v0.1) | **Owner**: AI Infra
> **来源**: [spec-diagnostic-infrastructure-v1.0.md](../specs/spec-diagnostic-infrastructure-v1.0.md) § 2.5

---

## 为什么需要这个索引？

调研发现 **6 条测试相关铁律在多个规则文件中重复出现**，agent 不知道哪条是"最新/权威"。

| 铁律 | 重复出现 | 权威源 (建议) |
|------|---------|--------------|
| 禁止直接 pytest | 4 处 (test_rules, SESSION_REMINDER, agent-bootstrap, test-case-standards) | [.trae/rules/test_rules.md#6-15](../../.trae/rules/test_rules.md) |
| test.py 是唯一入口 | 4 处 (同上) | [.trae/rules/test_rules.md#16-28](../../.trae/rules/test_rules.md) |
| 必须实时输出 + 分批 | 2 处 (test-observability-rules, SESSION_REMINDER#13-15) | [.trae/rules/test-observability-rules.md](../../.trae/rules/test-observability-rules.md) |
| 禁止 wait_for_timeout / sleep | 3 处 (SESSION_REMINDER#10, test-case-standards, test-script-quality-analysis) | [.trae/rules/test-case-standards.md](../../.trae/rules/test-case-standards.md) |
| Source Map 必须开 | 2 处 (SESSION_REMINDER#16, frontend-testing-standards) | [.trae/rules/frontend-testing-standards.md](../../.trae/rules/frontend-testing-standards.md) |
| happy-dom / MSW | 2 处 (SESSION_REMINDER#17-18, frontend-testing-standards) | [.trae/rules/frontend-testing-standards.md](../../.trae/rules/frontend-testing-standards.md) |

---

## 权威源逐条索引

### 1. 铁律: 禁止直接 pytest

**权威源**: `.trae/rules/test_rules.md` 第 6-15 行

**重复出现**:
- `.trae/rules/SESSION_REMINDER.md` #1
- `.trae/rules/agent-bootstrap.md` Step 3
- `.trae/rules/test-case-standards.md` (隐含)

**冲突时**: 以 `test_rules.md` 为准

---

### 2. 铁律: test.py 是唯一合法入口

**权威源**: `.trae/rules/test_rules.md` 第 22-28 行

**合法命令**:
```
python d:\filework\test.py --all
python d:\filework\test.py --failed
python d:\filework\test.py --skip
python d:\filework\test.py --unit
python d:\filework\test.py --integration
python d:\filework\test.py --status
python d:\filework\test.py --file <path>
python d:\filework\test.py --single <test_id>
```

**禁止** (由 conftest 硬阻断 `os._exit(1)`):
```
pytest
python -m pytest
npx playwright test  (绕过 test.py 入口)
```

---

### 3. 铁律: 长测试必须分批 + 实时输出

**权威源**: `.trae/rules/test-observability-rules.md`

**关键命令**:
```powershell
# Tee-Object 实时输出
python d:\filework\test.py --all 2>&1 | Tee-Object d:\filework\test_all.log | Out-Null

# 监控进度
Get-Content d:\filework\test_progress.json | ConvertFrom-Json

# Fail-Fast
python d:\filework\test.py --all --fail-fast --threshold 5
```

---

### 4. 铁律: 禁止 wait_for_timeout / sleep

**权威源**: `.trae/rules/test-case-standards.md` (第 X 节 "反模式清单")

**正确做法**:
```python
# [X] 错误
await page.wait_for_timeout(3000)
time.sleep(3)

# [OK] 正确
await page.wait_for_selector('.el-table', timeout=10000)
cli.wait_for_stable('.el-table')
```

**自动检测**: `tools/test_lint.py` (新工具, v1.0)

---

### 5. 铁律: 前端测试必须开 Source Map

**权威源**: `.trae/rules/frontend-testing-standards.md`

**配置** (vite.config.js):
```js
build: { sourcemap: 'hidden' }
test: { environment: 'happy-dom', sourcemap: true }
```

---

### 6. 铁律: 前端测试用 happy-dom + MSW

**权威源**: `.trae/rules/frontend-testing-standards.md`

**反模式**:
- ❌ jsdom (慢 2-3x)
- ❌ `vi.mock()` 模块 mock (脆弱)

**正确**:
- ✅ happy-dom
- ✅ MSW API mock

---

## 后续实施步骤

**Phase 2.5 实施** (待用户批准):

1. **在每个重复源文件顶部加 1 行 note** (不改内容):
   ```markdown
   > [NOTE] 本文档的"禁止 pytest"规则已在 [.trae/rules/test_rules.md](../../.trae/rules/test_rules.md) 详细描述。
   > 冲突时请以 test_rules.md 为准。
   ```
2. **不在排查 agent 运行时** 改 `.trae/rules/` (避免上下文重载)
3. **test_rules.md** 升级为唯一权威源, 其他文件改为引用

**当前阶段**: 本索引文件**只是索引**, 不动其他规则文件 (按用户要求"不影响正在排查的 agent")。

---

## CHANGELOG

| 日期 | 变更人 | 内容 |
|------|--------|------|
| 2026-06-15 | Batch2 Agent | 初版 |
