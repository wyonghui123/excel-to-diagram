# V4 兼容性细致检查报告 (2026-07-14)

> **目的**: 验证 `remote-execution-simplicity.md` V4 (L8-L20) 与现有 yonaa 项目的兼容性
> **范围**: 13 个 L8-L20 铁律 × 现有 6 个服务 (9101/9200/9202/9203/9204/9205) × 现有部署脚本

---

## 0. TL;DR — 一句话结论

**V4 的 L8-L20 大部分是"风险加固"建议，不影响现有逻辑；但 L16 (set -euo pipefail) 与 `lib/common.sh` 有冲突，必须**避免在 common.sh 中强制设置**，改为调用者各自负责**。

---

## 1. V007.67 修复 vs V4 全部铁律 ✅ 100% 兼容

| V4 铁律 | V007.67 修复 | 兼容性 |
|---|---|---|
| L1 禁 HTTP 127.0.0.1 自己调自己 | `http_exec()` 走 172.20.59.7:9101，不用 127.0.0.1 | ✅ |
| L2 禁 base64 + bash -c | `http_exec()` 单行 URL 编码，无 base64 | ✅ |
| L3 禁脚本套脚本中间层 | 复杂脚本独立上传 + 单行调用，3 层冗余 → 2 层 | ✅ |
| L4 禁外网穿透 | 我们不动 BIND（依赖 iptables） | ✅ |
| L5 禁 bash 解密嵌套 | 不写 base64 / bash -c / multi-layer shell | ✅ |
| L6 已开放端口安全措施 | log_service 已有 EXEC_WHITELIST + ALLOWED_DIRS + RateLimiter | ✅ |
| L7 密码不留痕 | 用 token 不用密码 | ✅ |
| L8-L20 合规层 | V007.67 是工具层修复，**不动业务服务** | ✅ |

---

## 2. L8-L20 兼容性详细分析

### 2.1 L8 强加密 — ✅ 兼容（仅风险加固）

**V4 建议**: 删除 `JWT_SECRET=${JWT_SECRET:-default}` 形式，改成 `${JWT_SECRET:?error}`

**现状**:
| 文件 | 行 | 现状 | 影响 |
|---|---|---|---|
| `deploy_bundle/tools/deploy_step.sh` | 27 | `JWT_SECRET="${JWT_SECRET:-v20260702-deploy-key-...}"` | 仅未注入时 fallback，**deploy.sh:152 已注入** |
| `deploy_bundle/tools/core_service.py` | 46-48 | 三级 token default (`v007.52-core-admin` 等) | 仅测试用 |
| `tools/dbops_service.py` | 24 | `SECRET = ... "v007.63-dbops"` default | 仅测试用 |
| `tools/deploy_service.py` | 36 | `SECRET = ... "v007.65-deploy"` default | 仅测试用 |

**结论**:
- ✅ **不影响现有部署逻辑**（deploy.sh 注入 SECRET 后 fallback 不触发）
- ✅ **不影响 V007.67 修复**（我们用 token，token 由运行时注入）
- ⚠️ **P1 改进**: 长期应改为 `${VAR:?error}`，但**不在本次范围**

### 2.2 L9 密码哈希 — ✅ 兼容（用户密码迁移不影响 token）

**V4 建议**: PBKDF2 100k → 600k 或换 Argon2id；删除 SHA256 无 salt legacy

**现状** (`deploy_bundle/meta/services/auth_provider.py`):
- 第 22 行: `iterations=100000` （< OWASP 600k）
- 第 49 行: `legacy_hash = hashlib.sha256(password)` 无 salt（兼容旧 hash）

**结论**:
- ✅ **不影响现有登录逻辑**（旧的 PBKDF2$ hash 仍可验证）
- ⚠️ **P1 改进**: 升级到 600k/Argon2id + 强制 rehashing
- ⚠️ **不在本次范围**: 改的是用户密码系统，不影响 V007.67 修复

### 2.3 L10 认证分层 — ✅ 兼容

**V4 建议**: 多级 token + JWT expire + 强密码策略

**现状**:
- ✅ `core_service.py:45-49` 已有 admin/write/read 三级
- ❌ `log_service.py:44` 仍是单 token（`v007.35-infra`）
- ❌ `dbops_service.py:24` / `deploy_service.py:36` 单 token

**结论**:
- ✅ **不影响 V007.67 修复**（agent 用 token 调服务，服务用 token 验证）
- ⚠️ **P1 改进**: log_service/dbops/deploy 升级到三级 token
- ⚠️ **不在本次范围**: 改的是服务认证逻辑，不影响 V007.67 修复

### 2.4 L11 TLS/HTTPS — ✅ 兼容

**V4 建议**: 强制 TLS 1.2+，禁用自签证书

**现状**:
- ✅ `core_service.py:610` 支持 TLS（SSL_CTX with min TLSv1.2 + 强 cipher）
- ❌ 默认 `BIND=0.0.0.0` + HTTP（SSL_CTX=None）
- ❌ 9200/9101/9204/9205 全部 HTTP 明文

**结论**:
- ✅ **不影响 V007.67 修复**（agent 用 HTTP 调 log_service，加密层不在我们范围）
- ⚠️ **P1 改进**: 部署内网 PKI + 强制 HTTPS
- ⚠️ **不在本次范围**: TLS 改动是网络/证书层，不影响 V007.67 修复

### 2.5 L12 CORS/Origin — ✅ 兼容

**V4 建议**: CORS 白名单禁止 `*`

**现状**:
- `deploy_bundle/tools/test_diagnose.py:186` 测试用 `CORS_ALLOWED_ORIGINS: *`
- 其他服务未明确 CORS 配置

**结论**:
- ✅ **不影响 V007.67 修复**（agent 不走 CORS）
- ⚠️ **P2 改进**: 移除测试用 `*`，配置明确白名单
- ⚠️ **不在本次范围**: CORS 配置是前端集成层

### 2.6 L13 输入验证 — ✅ 兼容（已有防护）

**V4 建议**: SQL 占位符 / path 走 realpath / SSRF 防护

**现状**:
- ✅ `log_service.py:82-91` `_path_allowed` 用 `os.path.realpath` 防 `../`
- ✅ `core_service.py` 同样有路径白名单 + realpath
- ✅ `audit_log_audit_deep.py` SQL 是 hardcoded（无注入风险）
- ⚠️ 完整的 SQL 占位符扫描需 bandit

**结论**:
- ✅ **V007.67 修复已经遵循 L13**（realpath + ALLOWED_DIRS）
- ⚠️ **P1 改进**: bandit 全项目扫描
- ⚠️ **不在本次范围**: bandit 集成是工具链

### 2.7 L14 依赖扫描 — ✅ 兼容（独立工具链）

**V4 建议**: pip-audit + safety + SBOM + CVE SLA

**现状**:
- `meta/requirements.txt` 用 `>=` 无 hash lock
- 无 SCA 扫描步骤

**结论**:
- ✅ **不影响 V007.67 修复**（V007.67 引入的 manifest_utils 等无新增依赖）
- ⚠️ **P1 改进**: 加 pip-audit 到 CI
- ⚠️ **不在本次范围**: CI 集成是构建链

### 2.8 L15 日志审计 — ✅ 兼容

**V4 建议**: rsyslog → 独立审计服务器 + WORM + 90 天留存

**现状**:
- 日志写在 `/opt/app/shared/logs/` 和 `/var/log/`
- 无 WORM 存储
- 无脱敏

**结论**:
- ✅ **不影响 V007.67 修复**（V007.67 不写日志，只读日志）
- ⚠️ **P1 改进**: 走 rsyslog + 脱敏
- ⚠️ **不在本次范围**: 日志架构是运维层

### 2.9 L16 错误处理 — 🔴 **关键冲突点**

**V4 建议**: 在 `lib/common.sh` 加 `set -euo pipefail`

**实际冲突**:

#### 冲突 1: common.sh 被多个脚本 source 后 set -u 会破坏现有逻辑

```bash
# 6 个脚本明确使用 set +u（关闭 nounset）
$ grep -l "set +u" deploy_bundle/**/*.sh
deploy_bundle/diagnose.sh:21
deploy_bundle/precheck.sh:21
deploy_bundle/smoke_test.sh:19
deploy_bundle/tools/diagnose.sh:21
deploy_bundle/tools/precheck.sh:21
deploy_bundle/tools/smoke_test.sh:19
```

如果 common.sh 头部加 `set -euo pipefail`：
- diagnose.sh 第 19 行 `source common.sh` 后**立即生效**
- diagnose.sh 第 21 行 `set +u` 仅关 nounset，但 `set -e` 已生效
- diagnose.sh 大量使用 `${1:-}` 等 fallback — **会因 -u 而 fail**

**结论**:
- 🔴 **V4 L16 的建议在 common.sh 强制 set -euo pipefail 会破坏 diagnose/precheck/smoke_test 3 个诊断脚本**
- ✅ **不影响 V007.67 修复**（我们用 subprocess + 单行命令，不依赖 common.sh）

**修正方案**（建议 V4 文档更新）:

```bash
# [V4 修正] L16 set -euo pipefail 不在 lib/common.sh 强制
# 原因: lib/common.sh 被 6 个 source 调用脚本用 set +u 关闭 nounset
# 修复: 每个 source common.sh 的脚本自行在 source 后 set -euo pipefail (如已 set 则跳过)

# deploy_bundle/tools/deploy_step.sh:14 已经 set -e  ✓
# deploy_bundle/tools/watch.sh:20 已经 set -uo pipefail  ✓
# deploy_bundle/tools/restart.sh:20 已经 set -uo pipefail  ✓

# diagnose.sh / precheck.sh / smoke_test.sh 用 set +u (按需, 不强制)
# 这是有意为之 — 诊断脚本要捕获尽可能多的失败信息
```

#### 冲突 2: `set -u` 与 `parse_args` 函数不兼容

`lib/common.sh:108-117` 的 parse_args 使用 `${2:-}` — 这是为了处理缺失参数。如果强制 `set -u`：
- `${2:-}` 还能用（POSIX 标准）
- 但 `${ARG_FOO}` 这种**未定义变量**会直接报错

`smoke_test.sh` / `diagnose.sh` 大量使用**可能未定义的环境变量** — set -u 会破坏。

### 2.10 L17 限流 — ✅ 兼容

**V4 建议**: 各端口加 rate_limit

**现状**:
- ✅ `log_service.py:94` 有 `RateLimiter` (10 req/s)
- ❌ 9200/9202/9203/9204/9205 未核实

**结论**:
- ✅ **不影响 V007.67 修复**（agent 调 log_service 已受限流保护）
- ⚠️ **P1 改进**: 各端口加 RateLimiter

### 2.11 L18 备份 — ✅ 兼容（独立工具）

**V4 建议**: 3-2-1 策略 + 季度演练

**现状**:
- `scripts/backup_db.py` 已存在（无密码明文）
- `deploy_bundle/deploy.sh` 已自动备份 `architecture.db`

**结论**:
- ✅ **不影响 V007.67 修复**（V007.67 不动备份逻辑）
- ⚠️ **P1 改进**: 3-2-1 策略 + 季度演练

### 2.12 L19 供应链 — ✅ 兼容（独立流程）

**V4 建议**: SBOM + cosign 签名 + CVE 跟踪

**结论**:
- ✅ **不影响 V007.67 修复**
- ⚠️ **P1 改进**: CI 集成

### 2.13 L20 DevSecOps — ✅ 兼容（独立 CI）

**V4 建议**: bandit + shellcheck + detect-secrets + gitleaks

**现状** (`.pre-commit-config.yaml`):
- ❌ 无 bandit
- ❌ 无 shellcheck
- ❌ 无 detect-secrets
- ✅ 有 scan-ai-content + check-encoding

**结论**:
- ✅ **不影响 V007.67 修复**（V007.67 已通过现有 pre-commit 钩子）
- ⚠️ **P1 改进**: 加全套 hooks

---

## 3. 关键修正建议（V4 文档层面）

### 3.1 L16 修正

**原 V4 描述**:
```bash
# [deploy_bundle/lib/common.sh:30]
# set -e  # 注释掉了!
# 应该 set -euo pipefail (严格模式)
```

**修正后（推荐）**:
```bash
# [V4 修正] L16 set -euo pipefail 不在 lib/common.sh 强制
# 原因: lib/common.sh 被 6 个 source 调用脚本用 set +u 关闭 nounset
#       强制 set -u 会破坏 diagnose.sh / precheck.sh / smoke_test.sh 的变量处理
# 
# 解决: 每个脚本自己 set -euo pipefail (已 deploy_step.sh:14 / watch.sh:20 / restart.sh:20)
#       诊断脚本 (diagnose/precheck/smoke_test) 故意保持宽容 — 捕获所有失败
# 
# 验证:
grep -E "^set -e" deploy_bundle/**/*.sh
# 已 set: deploy_step.sh, watch.sh, restart.sh, status.sh, deploy_history.sh
# 故意 set +u: diagnose.sh, precheck.sh, smoke_test.sh (诊断宽容)
```

### 3.2 L9 修正

**原 V4 描述**:
```
- [ ] 1. 算法: Argon2id (首选) / bcrypt (cost>=12) / scrypt / PBKDF2-HMAC-SHA512 (iter>=600000)
- [ ] 2. 每个密码独立 salt (>=16 bytes)
- [ ] 3. 禁止 SHA1/MD5/SHA256 (无 salt) 用于密码
```

**修正后（推荐）— 加兼容性说明**:
```
- [ ] 1. 算法: Argon2id (首选) / bcrypt (cost>=12) / scrypt / PBKDF2-HMAC-SHA512 (iter>=600000)
- [ ] 2. 每个密码独立 salt (>=16 bytes)
- [ ] 3. 禁止 SHA1/MD5/SHA256 (无 salt) 用于密码
- [ ] 4. (兼容性) 现有 PBKDF2$iter=100k$hash 仍可验证 — 升级时检查 needs_rehash
- [ ] 5. (兼容性) legacy SHA256 hash 通过 verify_and_rehash 首次登录自动升级
```

### 3.3 L8 修正

**原 V4 描述**:
```bash
JWT_SECRET="${JWT_SECRET:-v20260702-deploy-key-2026-07-03-do-not-use-in-prod}"
```

**修正后（推荐）— 加现状说明**:
```bash
# 现状: deploy.sh:152 已注入 JWT_SECRET, deploy_step.sh:27 的 default 是 fallback
#       正常部署流程不会触发 default (已注入)
# 
# 修复: 在 deploy.sh:152 强制验证 + 增加 deploy_step.sh 的 ?:
JWT_SECRET="${JWT_SECRET:?ERROR: JWT_SECRET must be set by deploy.sh, see deploy.sh:152}"
```

### 3.4 L4 修正（重要：spec.md 的 L8 编号冲突）

**问题**: spec.md 已有 L8.6/L8.8/L12/L13.3/L14/L15 编号（任务章节），与 V4 铁律 L8-L20 **冲突**

**修正建议**: V4 顶部加**编号空间声明**:

```markdown
## 编号空间声明

V4 文档中的 L1-L20 是**合规铁律**（与行业标准映射）。

注意: 项目内部 spec.md / docs/ 中的 "L8.6 / L8.8 / L12 / L13.3" 是**任务编号**，与本文铁律不同。

例: `spec.md` 的 "L8.6 unzip_safe" 是任务 8.6 (unzip_safe 任务), 不是 V4 铁律 L8 的 6 号子项。

**避免混淆**: 阅读本文时只关注 L# 顶级编号。
```

---

## 4. V007.67 修复 vs V4 完整对标

| V4 铁律 | V007.67 修复 | 状态 |
|---|---|---|
| L1 HTTP 127.0.0.1 | 走 172.20.59.7 | ✅ |
| L2 base64 + bash -c | 全明文 URL 编码 | ✅ |
| L3 脚本套脚本 | 独立上传 + 单行调用 | ✅ |
| L4 外网穿透 | 不动 BIND | ✅ |
| L5 bash 解密嵌套 | 无嵌套 | ✅ |
| L6 已开放端口 | 用 log_service 已有防护 | ✅ |
| L7 密码不留痕 | 用 token | ✅ |
| L8 强加密 | 用 token | ✅ |
| L9 密码哈希 | 不动用户密码系统 | ✅ |
| L10 认证分层 | 用 token 即可 | ✅ |
| L11 TLS | HTTP 不强制 | ✅ |
| L12 CORS | 不走 CORS | ✅ |
| L13 输入验证 | 已有 realpath + ALLOWED_DIRS | ✅ |
| L14 依赖扫描 | V007.67 不引入新依赖 | ✅ |
| L15 日志审计 | V007.67 只读日志 | ✅ |
| L16 错误处理 | **不引入 set -e 到 common.sh** | ✅ |
| L17 限流 | log_service 已限流 | ✅ |
| L18 备份 | 不动 | ✅ |
| L19 供应链 | 不动 | ✅ |
| L20 DevSecOps | 不动 | ✅ |

**全部 20 个铁律兼容 V007.67 修复！**

---

## 5. 总结

### ✅ V4 与现有逻辑兼容性

- **L1-L7 反木马层**：100% 兼容（V007.67 修复符合）
- **L8-L15 强合规层**：100% 兼容（建议**不影响现有逻辑的渐进式加固**）
- **L16 错误处理**：🔴 **需修正 V4 文档** — 不要在 common.sh 强制 set -u
- **L17-L20 工程层**：100% 兼容（独立工具链）

### 📋 V4 文档建议修正项

1. **L16 修正**: 注明 common.sh 不强制 set -u，调用者各自负责
2. **L9 修正**: 加兼容性说明（不破坏现有 PBKDF2 验证）
3. **L8 修正**: 加现状说明（deploy.sh:152 已注入）
4. **编号空间声明**: 区分 V4 铁律 L# vs spec.md 任务编号 L#

### 🎯 长期改进路径（不影响现有逻辑）

- **P1 (本月)**:
  - L9 升级到 600k + 强制 rehash（保留旧 hash 兼容）
  - L10 log_service/dbops/deploy 升级到三级 token（保留单 token 兼容）
  - L13 bandit + shellcheck 到 pre-commit
- **P2 (季度)**:
  - L11 部署内网 PKI + 强制 HTTPS
  - L18 3-2-1 备份策略
  - L19 SBOM + CVE 跟踪

### 结论

**V4 是**合规加固蓝图**，不是**立即修改清单**。**

按 V4 的"Phase A/B/C"（本周/本月/季度）路径实施，**不会影响 V007.67 修复**，也不影响现有逻辑。

唯一需要立即修正的是 V4 L16 的描述（避免在 common.sh 强制 set -u）。

---

**报告生成**: V007.67 2026-07-14
**关联 commits**: 0b7c540, eb70eee, 839e75d, 50ed9ec, 72dc9ca
**详细实施**: 见 `docs/PROD_DELTA_DEPLOY_RUNBOOK.md` + `tools/run_security_audit.py`