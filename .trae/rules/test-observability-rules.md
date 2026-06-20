---
alwaysApply: false
description: "测试可观测性规范：trace_id、结构化日志、metrics、diagnostics"
globs: "meta/tests/**/*,meta/core/trace_id*,meta/api/diagnostics*"
---

# 测试可观测性规范

> **智能体在运行长测试时必须保证可观测性：分批、实时输出、过程检查、快速中断。**

## 为什么需要测试可观测性？

### 问题场景

```
[23:00] 智能体开始运行 E2E 测试
[23:00] 智能体开始等待...
[23:10] 测试还在跑...
[23:10] 智能体不知道：
         - 跑到哪个 case 了？
         - 当前有多少失败？
         - 还需多久完成？
         - 要不要中断？
[23:15] 终于跑完，发现有 10 个失败
[23:15] 智能体开始挨个修复
[23:30] 修复完又跑一遍，发现 5 个新失败
```

**问题本质**：
- **黑盒运行** - 测试期间没有任何反馈
- **反馈延迟** - 失败要等 5-10 分钟才看到
- **无法决策** - 中途不知道是否应该中断
- **浪费时间** - 失败的测试也要跑完

## 解决方案：五要素

| 要素 | 说明 | 工具 |
|------|------|------|
| **1. 分批运行** | 把长测试分成 5-10 批 | test.py 内置 |
| **2. 实时输出** | 每个测试都输出，不等最后 | Tee-Object |
| **3. 过程检查** | 每批后查看进度文件 | cat test_progress.json |
| **4. 快速中断** | 失败率超阈值立即停止 | Fail-Fast |
| **5. 可视化报告** | 进度条、ETA、统计 | test_live.md |

## 1. 分批运行

### 原则

**不要一次性运行超过 5 分钟的测试**。如果预计 > 5 分钟，必须分批。

### 分批策略

| 测试类型 | 数量 | 单批 | 批数 | 总时间 |
|---------|------|------|------|--------|
| 单元测试 | < 100 | 50 | 2 | < 2 分钟 |
| 集成测试 | 100-500 | 30 | 5-15 | 5-10 分钟 |
| E2E 测试 | 10-50 | 5 | 2-10 | 5-30 分钟 |

### 实现方式

```bash
# [X] 错误：一次性跑完全部 E2E
python test.py --e2e  # 30 分钟，没有可观测性

# [OK] 正确：分批运行
python test.py --e2e --batch-size 5 --fail-fast
# 每 5 个测试一批，失败快速中断

# [OK] 正确：分片（用于并行）
python test.py --e2e --shard 1/4  # 第 1 片，共 4 片
```

## 2. 实时输出

### 原则

**测试期间的每个 case 都应该有输出**，而不是最后一次性输出。

### 错误做法

```bash
# [X] 错误：输出被截断或丢失
npx playwright test --project=features 2>&1 | Out-String | Select-String -Pattern "passed|failed"

# 智能体看到的是最后 80 行，可能错过关键错误
```

### 正确做法

```bash
# [OK] 正确：实时输出到终端 + 保存到文件
python test.py --all 2>&1 | Tee-Object d:\filework\test-results\run-$(Get-Date -Format 'yyyyMMdd-HHmmss').log

# 这样可以：
# 1. 实时看到测试输出
# 2. 完整保存到文件用于后续分析
# 3. Ctrl+C 中断后日志仍然保存
```

### 更精细的实时输出

```bash
# [OK] 更好：用 pytest -v 显示每个测试名
python -m pytest -v --tb=short tests/e2e/test_user.py

# [OK] 更好：用 pytest-sugar 进度条
python -m pytest tests/e2e/ -p sugar

# [OK] 更好：用 --durations=N 显示最慢的 N 个测试
python -m pytest tests/e2e/ --durations=10
```

## 3. 过程检查

### 原则

**每批结束后必须检查进度**：
- 跑了几批？
- 当前在哪个 case？
- 失败率多少？
- 还要多久？

### 检查方法

#### 方法 1：查看进度文件

```bash
# 实时查看进度
Get-Content d:\filework\test_progress.json | ConvertFrom-Json
```

进度文件格式：

```json
{
  "phase": "executing",
  "stage": "e2e",
  "completed": 15,
  "total": 30,
  "percentage": 50.0,
  "current_test": "test_user_login",
  "current_file": "tests/e2e/test_user.py",
  "elapsed_seconds": 135,
  "estimated_remaining": 135,
  "stats": {
    "passed": 13,
    "failed": 1,
    "skipped": 1
  },
  "fail_fast": {
    "should_interrupt": false,
    "reason": null
  }
}
```

#### 方法 2：查看实时报告

```bash
# Markdown 格式的实时报告
Get-Content d:\filework\test_live.md
```

#### 方法 3：自动刷新（高级）

```bash
# PowerShell 自动刷新（每 5 秒）
while ($true) {
    Clear-Host
    Get-Content d:\filework\test_progress.json | ConvertFrom-Json | Format-List
    Start-Sleep 5
}
```

## 4. 快速中断（Fail-Fast）

### 原则

**当失败率超过阈值时立即停止**。不要等跑完才知道大量失败。

### 阈值配置

| 测试类型 | 立即中断阈值 | 错误类型权重 |
|---------|------------|------------|
| 单元测试 | 1 个失败 | ImportError=10x, AssertionError=1x |
| 集成测试 | 5 个失败 | TimeoutError=5x, ConnectionError=3x |
| E2E 测试 | 10 个失败 | PageError=5x, AssertionError=1x |

### 触发场景

```python
# Fail-Fast 触发条件
if failed >= total_threshold:
    return True, "总失败数 >= 阈值"

if critical_error_detected:
    return True, "检测到严重错误（ImportError 等）"

if consecutive_batches_failed >= 3:
    return True, "连续 3 批都失败"
```

### 使用方式

```bash
# 启用 Fail-Fast
python test.py --all --fail-fast

# 自定义阈值
python test.py --all --fail-fast --threshold 5
```

## 5. 可视化报告

### 实时进度条

```
[██████████░░░░░░░░░░] 50.0% | 15/30 | [OK]13 [X]1 ⏭️1 | ETA 2m 15s
```

### Markdown 实时报告（test_live.md）

```markdown
# Test Dashboard

**[WAIT] RUNNING** | e2e | Updated: 23:55:18

```
[██████████░░░░░░░░░░] 50.0%
  Total:       30
  Done:        15  (50.0%)
  Passed:      13
  Failed:       1
  Skipped:      1
  Elapsed:  2m 15s
  ETA:      2m 15s
```
```

### HTML 报告（pytest-html）

```bash
# 生成 HTML 报告
python -m pytest tests/ --html=test-results/report.html --self-contained-html

# 浏览器打开
start test-results/report.html
```

## 完整工作流

### 智能体运行长测试的标准流程

```bash
# 1. 启用实时输出（tee 到文件）
python test.py --e2e --batch-size 5 --fail-fast 2>&1 | Tee-Object d:\filework\test-results\e2e-$(Get-Date -Format 'yyyyMMdd-HHmmss').log

# 2. 后台运行（另一个终端监控进度）
# 智能体可以：
#   - 每 30 秒 read test_progress.json
#   - 决定是否继续/中断
#   - 检查失败情况

# 3. 检查 Fail-Fast 决策
Get-Content d:\filework\test_progress.json | ConvertFrom-Json | Select-Object -ExpandProperty fail_fast

# 4. 如果失败率 > 50%，立即停止
if (failed/total > 0.5) { Stop-Process ... }
```

### 关键决策点

| 决策点 | 检查内容 | 决策 |
|--------|---------|------|
| 开始前 | 服务是否健康？ | 不健康 → restart |
| 跑 25% 时 | 失败率？ | > 10% → 检查根因 |
| 跑 50% 时 | 已失败数量？ | > 5 → Fail-Fast |
| 跑 75% 时 | 当前 case 慢？ | > 5 分钟 → 检查 hang |
| 跑 100% 时 | 总耗时？ | > 30 分钟 → 拆分为单元测试 + 集成测试 |

## 常见误区

### 误区 1：跑完才知道结果

```bash
# [X] 错误
python test.py --all
# 跑 10 分钟后才发现有 50 个失败

# [OK] 正确
python test.py --all --fail-fast
# 跑到 5 个失败时立即停止
```

### 误区 2：输出过滤丢失信息

```bash
# [X] 错误
npx playwright test | Out-String | Select-String "passed|failed"
# 丢失了 stack trace、console error 等关键信息

# [OK] 正确
npx playwright test | Tee-Object test.log
# 保留完整输出
```

### 误区 3：不分层全跑

```bash
# [X] 错误
python test.py --all  # 跑 1800 个测试，10 分钟

# [OK] 正确
python test.py --unit  # 先跑 70% 单元测试（< 1 分钟）
python test.py --integration  # 再跑 20% 集成测试（5-10 分钟）
python test.py --e2e --batch-size 5  # 最后跑 10% E2E（分批）
```

## 紧急情况处理

### 测试 hang 住

```bash
# 症状：进度文件超过 5 分钟没更新
# 解决：
# 1. 杀掉测试进程
Get-Process python | Where-Object { $_.CommandLine -like "*test.py*" } | Stop-Process -Force

# 2. 检查服务健康
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 status

# 3. 重启服务（如需要）
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 restart

# 4. 改用 --failed 跑剩余
python test.py --failed
```

### 失败率突然飙升

```bash
# 症状：从 0% 突然 50%
# 解决：
# 1. 立即停止
Stop-Process -Name python -Force

# 2. 查看最近的修改
git diff HEAD~5

# 3. 回滚到上一个 stable 版本
git checkout HEAD~5 -- meta/

# 4. 重新跑
python test.py --unit
```

## 工具支持

### 已有的工具

- **test.py** - 统一入口，支持分批、Fail-Fast
- **test_monitor_enhanced.py** - TestMonitor 类，实时进度
- **test_progress.json** - 实时进度数据
- **test_live.md** - Markdown 实时报告
- **service_manager.ps1** - 服务管理

### 推荐工具

- **pytest-sugar** - 进度条插件
- **pytest-html** - HTML 报告
- **pytest-xdist** - 并行执行
- **pytest-watch** - 文件变化自动重跑

## 检查清单

运行长测试前的检查清单：

- [ ] 服务健康？
- [ ] 数据库快照？
- [ ] 已分批？每批 < 5 分钟？
- [ ] 已启用 Fail-Fast？
- [ ] 已 tee 到日志文件？
- [ ] 已知道如何中断？

Sources:
- [pytest-balance - 智能测试分配](https://pypi.org/project/pytest-balance/)
- [pytest-xdist - 并行测试](https://theneuralbase.com/llm-testing/learn/advanced/parallel-test-shards/)
- [OneUptime - OpenTelemetry 测试监控](https://oneuptime.com/blog/post/2026-02-06-opentelemetry-test-suite-flaky-detection/view)
- [TestUnity - 慢测试 7 快速修复](https://blog.testunity.com/slow-test-execution-7-quick-fixes/)
- [可观测性设计](https://blog.csdn.net/2501_94436372/article/details/160474103)
