# V4 L16 修正补丁 (2026-07-14)

> **目的**: 修正 `remote-execution-simplicity.md` V4 中 L16 在 `lib/common.sh` 的建议，避免破坏现有逻辑
> **范围**: 仅修正 L16 段落（约 30 行），不影响其他 L8-L20

---

## 1. 问题

V4 L16 原文建议:
```bash
# set -e  # 注释掉了!
# 应该 set -euo pipefail (严格模式)
```

但 `lib/common.sh` 被 6 个脚本 source，其中 3 个用 `set +u`（关闭 nounset）:

```
deploy_bundle/diagnose.sh:21        # source common.sh + set +u
deploy_bundle/precheck.sh:21        # source common.sh + set +u
deploy_bundle/smoke_test.sh:19      # source common.sh + set +u
deploy_bundle/tools/diagnose.sh:21  # 同上
deploy_bundle/tools/precheck.sh:21  # 同上
deploy_bundle/tools/smoke_test.sh:19 # 同上
```

如果在 `common.sh` 头部加 `set -euo pipefail`：
- `set -u` 会使诊断脚本因访问未定义变量而 fail
- `diagnose.sh` / `precheck.sh` / `smoke_test.sh` 是**生产诊断核心**
- 破坏它们 = 部署后无法定位问题

---

## 2. 修正方案

### 2.1 V4 L16 段落替换

**原段落** (`remote-execution-simplicity.md` 第 696-714 行):

```markdown
### 7.9 L16 错误处理信息脱敏

**对应标准**: OWASP A09:2021 / CIS 16

**当前代码风险** (`deploy_bundle/lib/common.sh:30`):
```bash
# set -e  # 注释掉了!
# 应该 set -euo pipefail (严格模式)
```

**判定标准**:
```
[ ] 1. 生产关闭 debug (FLASK_DEBUG=false, FLASK_ENV=production)
[ ] 2. 500 错误统一响应: {"error": "internal_error", "trace_id": "uuid"}, 不含 stack trace
[ ] 3. shell 脚本 set -euo pipefail
[ ] 4. Python 自定义全局 ErrorHandler
[ ] 5. 错误监控: Sentry / 自建 syslog (带 trace_id)
```
```

**修正后**:

```markdown
### 7.9 L16 错误处理信息脱敏

**对应标准**: OWASP A09:2021 / CIS 16

**⚠️ 重要修正（2026-07-14 PM）**: 原版建议 `deploy_bundle/lib/common.sh:30` 改 `set -euo pipefail`，
**会破坏现有诊断脚本**。`common.sh` 被 6 个脚本 source，其中 3 个故意用 `set +u` 关闭 nounset
（diagnose/precheck/smoke_test，要捕获所有失败信息）。强制 set -u 会因访问未定义变量而 fail。

**正确做法**: 各自脚本显式声明严格模式:

```bash
# deploy_bundle/tools/deploy_step.sh:14
set -e  # ✓ 已设置

# deploy_bundle/tools/watch.sh:20
set -uo pipefail  # ✓ 已设置

# deploy_bundle/tools/restart.sh:20
set -uo pipefail  # ✓ 已设置

# diagnose.sh / precheck.sh / smoke_test.sh 故意保留 set +u
# 原因: 这些是生产诊断脚本, 需要宽容地处理可能缺失的变量, 收集所有失败信息
```

**判定标准**:
```
[ ] 1. 生产关闭 debug (FLASK_DEBUG=false, FLASK_ENV=production)
[ ] 2. 500 错误统一响应: {"error": "internal_error", "trace_id": "uuid"}, 不含 stack trace
[ ] 3. shell 脚本 set -euo pipefail (除诊断脚本外)
[ ] 4. lib/common.sh 不强制 set -u (被 6 个 source 调用)
[ ] 5. Python 自定义全局 ErrorHandler
[ ] 6. 错误监控: Sentry / 自建 syslog (带 trace_id)
```

**当前已合规**:
- ✅ `deploy_step.sh:14` set -e
- ✅ `watch.sh:20` set -uo pipefail
- ✅ `restart.sh:20` set -uo pipefail
- ✅ `status.sh:20` set -uo pipefail
- ✅ `deploy_history.sh:14` set -uo pipefail
- ✅ 5/12 部署脚本已严格模式
- ⚠️ diagnose.sh / precheck.sh / smoke_test.sh 故意宽容 (诊断)
```

### 2.2 V4 Phase A 移除 L16 P0

**原 Phase A** (L16 P0):
```
- [ ] **L16/P0**: `# set -e` 取消注释, 所有 lib/common.sh
```

**修正后 Phase A** (移除 L16 P0):
```
- [ ] **L16/P0**: ❌ 已修正 (common.sh 不强制 set -u, 已在 5/12 脚本设严格模式)
```

### 2.3 V4 顶部加编号空间声明

**新增段落** (插入到 V4 "0. TL;DR" 之后):

```markdown
### 编号空间声明

V4 文档中的 L1-L20 是**合规铁律**（与行业标准映射）。

注意: 项目内部 spec.md / docs/ 中的 "L8.6 / L8.8 / L12 / L13.3 / L14 / L15" 是**任务章节编号**，与本文铁律不同。

例: `spec.md` 的 "L8.6 unzip_safe" 是任务 8.6 (unzip_safe 任务), **不是** V4 铁律 L8 的 6 号子项。

**避免混淆**: 阅读本文时只关注 L# 顶级编号。
```

---

## 3. 验证脚本（部署前用）

```bash
# 验证: 已 set -euo pipefail 的脚本
for f in $(grep -l "set -euo pipefail\|set -e$\|set -uo pipefail" deploy_bundle/**/*.sh); do
    echo "✓ $f"
done

# 验证: 诊断脚本故意 set +u
for f in diagnose.sh precheck.sh smoke_test.sh; do
    if grep -q "set +u" $f; then
        echo "✓ $f (intentionally lenient)"
    fi
done
```

---

## 4. 相关文档

- 主报告: `docs/V4_COMPATIBILITY_REPORT.md`
- V4 完整文档: `.trae/rules/remote-execution-simplicity.md`
- V007.67 修复: 6 commits (a37f1bd, 1d9da66, b2f9f43, 66a0605, 72dc9ca, 50ed9ec)
- V007.67 Delta 部署: commits 0b7c540, eb70eee, 839e75d

---

**补丁作者**: V007.67 Agent
**日期**: 2026-07-14
**优先级**: P1 (本周内更新 V4 文档)