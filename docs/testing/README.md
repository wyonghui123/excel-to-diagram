# 测试文档入口（路由页）

> 用途：**只回答「读什么、何时读」**。测试规则、执行命令、事故记录各自有唯一真源，本文不复制其内容。
> 维护约定：结构变化时改本页；实现细节只写进 `test-efficiency-spec.md`。
> 最后更新：2026-11-10（v4.6，P1-1/P1-2）

---

## 1. 分层与阅读顺序

| 层 | 内容 | 何时读 | 真源 |
|---|---|---|---|
| L0 | 11 条铁律 + 会话体检/槽位 | **每次会话开始**（自动加载） | `d:\filework\.trae\rules\IRON-RULES-CHEATSHEET.md`、`SESSION_REMINDER.md` |
| L1 | 测试执行规范（唯一入口、实时输出、用例规范、数据规范） | 写/跑任何测试前 | `.trae/rules/test_rules.md`、`test-observability-rules.md`、`test-case-standards.md`、`test-data-rules.md` |
| L1.5 | 测试工具与夹具用法 | 写测试代码时查夹具/工具 | `meta/tests/TESTING_TOOLS_GUIDE.md`、`meta/tests/shared/`（16 个模块） |
| L2 | 测试执行效率优化规格（20+ 项决策与实测证据） | 改测试基础设施 / 排查「慢、卡、结果不可信」 | 本目录 `test-efficiency-spec.md` |
| L3 | 启动分段基线数据 | 改 `create_app()` 链路或守卫/缓存后做对比 | 本目录 `startup-baseline.json`（**工具生成，禁止手改**） |

历史索引说明：`docs/rules/TESTING_INDEX.md`（2026-06-15）只登记「6 条测试铁律的权威源」，属 L1 的补充索引，与本文不冲突。

---

## 2. 按任务路由

| 我要做什么 | 先读 | 再执行 |
|---|---|---|
| 跑全量 / 修失败 | L0 + L1；spec §0 结论摘要 | `python d:\filework\test.py --all` → `--failed`（修复后只跑 `--failed`） |
| 只跑一个文件 | L1「唯一入口」 | `python d:\filework\test.py --file meta/tests/<x>.py`（多文件 `--file` 是同进程串行，**不能作为全量证据**） |
| 新增测试文件 | L1 用例规范 + L1.5 夹具指南 | 写完后跑 `python scripts/lint_tests.py --max-detail 5` |
| 新增/修改测试态环境开关 | 本文 §3 + `meta/tests/shared/env_flags.py` 头部注释 | 在 `FLAGS` 加一条 → `python meta/tests/shared/env_flags.py --json` 自查 |
| 新增「声明内容哈希守卫」/缓存 | `meta/core/declaration_guard.py` 头部注释 + spec §11 v4.5 | 跑 `python scripts/debug/verify/startup_breakdown.py --skip-preflight --json docs/testing/startup-baseline.json` 与基线对比 |
| 排查「测试跑不完 / Total 为 0 / 假成功退出」 | spec §3 根因模型（R1-R12） | 按根因编号定位，不要先怀疑用例代码 |
| 判断某文件为何被整文件 skip | spec §11 v2.8-v3.5（raw-SQL 守卫恢复记录） + conftest 守卫 | 看文件头是否声明 `ALLOW_RAW_SQL`；DML 优先走 `factories/_raw_sql_bridge.py` |
| 查启动慢在哪一段 | `startup-baseline.json` 的 `runs[0].sections` | `python scripts/debug/verify/startup_breakdown.py --verbose` |

---

## 3. 测试基础设施资产（新增，勿重复造）

| 资产 | 作用 | 入口 |
|---|---|---|
| `meta/core/declaration_guard.py` | 统一守卫工具包：确定性哈希、版本+内容双因子、存在性前提、失败降级、全量成功后才落守卫、`GUARD_FORCE=1` 逃生 | `python -m meta.core.declaration_guard --db <db> --status` |
| `meta/tests/shared/env_flags.py` | 测试态环境开关注册表（**单一声明源**），conftest 只调用 `apply_early_flags()` / `apply_test_flags()` | `python meta/tests/shared/env_flags.py --json` |
| `scripts/lint_tests.py` | 9 项可执行 lint（syntax/duplicate-file/duplicate-test-def/inline-sql/sleep/missing-marker/no-assert/direct-create-app/hardcoded-version-id） | `python scripts/lint_tests.py --max-detail 5 [--fail-on high]` |
| `scripts/debug/verify/startup_breakdown.py` | `create_app()` 分段计时探针，输出 first/warm 两轮基线 | `python scripts/debug/verify/startup_breakdown.py --skip-preflight --json docs/testing/startup-baseline.json` |

约束提醒：
- `scripts/debug/` 整目录被 `.gitignore` 忽略，新增脚本需 `git add -f` 才入库（当前 `verify/startup_breakdown.py` 已强制入库）。
- 新增测试态开关**只改** `env_flags.py`，不要在测试文件里散落 `os.environ[...] = ...`；需要反例的用例自行保存-修改-恢复。
- 守卫命中前提必须是「哈希一致 **且** 期望对象存在」；只比哈希会在库被删表后永久跳过（见 spec v4.0 §③）。

---

## 4. 文件清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `README.md` | 手写 | 本路由页 |
| `test-efficiency-spec.md` | 手写 | 实现规格 + §11 变更记录（唯一决策日志，只追加不改写） |
| `startup-baseline.json` | 工具生成 | `startup_breakdown.py` 输出；改链路后重新生成并 review diff |