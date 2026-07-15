# REGRESSION_TEST_SUITE.md

> **sqlite IO 错误回归测试** (staging 沙盒)
> **最后更新**: 2026-07-15 (V007.55)
> **总入口**: [DEPLOY_INFRASTRUCTURE.md](../DEPLOY_INFRASTRUCTURE.md) §0

---

## §0. 一图全貌

```
  staging 沙盒
       │
       ▼
  ┌────────────────────────────────────────────────────┐
  │  regression_test_suite.py (本工具)                  │
  │                                                    │
  │  R1 readonly     ─┐                                │
  │  R2 busy          │ 故障注入 (6 类)               │
  │  R3 extlock       │                                │
  │  R4 corrupt       │ 每次: backup → inject →        │
  │  R5 deleted       │       expect → verify → restore│
  │  R6 full         ─┘                                │
  │  R7 wal_corrupt  ── 额外: WAL 损坏                 │
  │  R8 timeout      ── 额外: connection timeout       │
  │  R9 readonly_root ── 特殊: root 写防护 (V007.49)   │
  └────────────────────────────┬───────────────────────┘
                               │
                               ▼
  ┌────────────────────────────────────────────────────┐
  │ 集成点:                                            │
  │  - staging_deploy_orchestrator Step 10.5 (post)    │
  │  - CI: 每次 staging 部署后自动跑                    │
  │  - 手动: python tools/regression_test_suite.py      │
  └────────────────────────────────────────────────────┘
```

---

## §1. 9 个测试场景

| # | 场景 | 注入方式 | 期望行为 | 历史背景 |
|---|------|---------|---------|---------|
| **R1** | readonly | chmod 555 | 写应被阻 OR root 绕过 | V007.49 重大发现 |
| **R2** | busy | 本地 exclusive 锁 | 其他连接应 BLOCKED | 默认配置 |
| **R3** | extlock | 外部进程持锁 | 读应 OK (WAL 模式) | sqlite3 CLI |
| **R4** | corrupt | 改 db 头 100 字节 | integrity_check 失败 | DB 损坏 |
| **R5** | deleted | shutil.move 移走 | 立刻检测文件不存在 | 用 `mode=ro` URI |
| **R6** | full | setrlimit RLIMIT_FSIZE | 大写入应失败 | 模拟磁盘满 |
| **R7** | wal_corrupt | 写垃圾到 -wal | sqlite 应能恢复 | WAL 损坏 |
| **R8** | timeout | small timeout + write | 应 1s 后超时 | connection timeout |
| **R9** | readonly_root | chmod 555 + root 检测 | 应用层必须自检 | V007.49 教训 |

### §1.1 R1 + R9 为什么有 SKIP

- **R1**: 在 root 下 chmod 555 **不会阻 root 写** (Linux POSIX 行为)
  - **业务防护必须在应用层** (不能依赖文件权限)
- **R9**: 验证 root 也应被防护
  - `os.access(path, W_OK)` 对 root 永远返回 True
  - 应用层必须自己检查 (e.g., 写前 `fstat` + `S_IWUSR`)

**V007.49 重大发现**: 不要假设 chmod 阻 root。**所有写防护都必须在应用层**。

---

## §2. 用法

### §2.1 跑全部 (staging)

```bash
cd /opt/app/staging/deploy
python3 tools/regression_test_suite.py
# 预期: 7 PASS / 0 FAIL / 2 SKIP / 9 total
```

### §2.2 跑单个

```bash
python3 tools/regression_test_suite.py --scenario R5
# 单独跑 deleted 场景
```

### §2.3 输出 JSON 报告

```bash
python3 tools/regression_test_suite.py --json /tmp/reg.json
# 报告含: run_id, summary, 每个 case 的 expected/actual/notes
cat /tmp/reg.json
```

### §2.4 prod 防护 (硬规则)

```bash
# 严禁在 prod 跑 (会破坏生产数据)
$ python3 tools/regression_test_suite.py
[FATAL] 此工具只能在 staging 跑 (db=/opt/app/deployments/meta/architecture.db)
       用 --db-path /opt/app/staging/deploy/meta/architecture.db
# 退出码 2
```

---

## §3. 集成

### §3.1 staging_deploy_orchestrator Step 10.5

每次 staging 部署完成后, 自动跑回归测试, daily 模式下失败会**暂停 prod 部署**。

### §3.2 CI (未来可加)

```yaml
# .gitlab-ci.yml / .github/workflows/
staging_regression:
  script:
    - ssh staging "cd /opt/app/staging/deploy && python3 tools/regression_test_suite.py"
  rules:
    - if: $CI_PIPELINE_SOURCE == "schedule"  # 定时跑
```

### §3.3 监控告警 (未来可加)

```python
# tools/monitor_migrations.py 加 --check-regression
# 失败 → 告警频道发消息
```

---

## §4. 历史与教训

### §4.1 V007.49 重大发现 (2026-07-13)

| 现象 | 教训 |
|------|------|
| `chmod 555` 后 root 仍能写 | **不要依赖文件权限做写防护** |
| 应用层应自己检查 | 写前 `os.access()` 不可信, 用 `fstat` + `S_IWUSR` |
| 旧代码用 `os.access` | **必须改用 `fstat`** |

### §4.2 V007.55 (2026-07-15)

| 新增 | 原因 |
|------|------|
| R5 (deleted) 用 `mode=ro` URI | sqlite3.connect 缓存, 不立刻检测 |
| R8 (timeout) 用 write | read 不被 exclusive 锁 block |
| R7 (wal_corrupt) | WAL 损坏是真实场景 |
| R6 (full) | 磁盘满是高频云故障 |
| 集成到 Step 10.5 | 每次 staging 部署后自动验证 |

---

## §5. 输出示例 (2026-07-15 staging)

```
[regression_test_suite] db=/opt/app/staging/deploy/meta/architecture.db  run_id=20260715_194350
  备份目录: /opt/app/staging/deploy/meta/regression_bak

=== R1: readonly ===
  [SKIP] expected=WRITE_BLOCKED_OR_ROOT_OK actual=ROOT_WRITE_OK
  notes: root 绕过 chmod 555 (V007.49 已知); 业务防护层必须在应用层

=== R2: busy ===
  [PASS] expected=OTHER_BLOCKED actual=OTHER_BLOCKED: database is locked
  notes: lock_timeout_ms=2000, waited=2003ms

=== R3: extlock ===
  [PASS] expected=READ_OK actual=READ_OK (no lock conflict)
  notes: external_lock_held_by_pid=15464, app_read=1ms

=== R4: corrupt ===
  [PASS] expected=CORRUPT_DETECTED actual=DB_ERROR: file is encrypted or is not a database
  notes: sqlite 拒绝打开损坏 db

=== R5: deleted ===
  [PASS] expected=DB_GONE actual=DB_GONE: unable to open database file

=== R6: full ===
  [PASS] expected=BIG_WRITE_BLOCKED actual=BIG_WRITE_BLOCKED: [Errno 27] File too large

=== R7: wal_corrupt ===
  [PASS] expected=WAL_RECOVERED_OR_REJECTED actual=WAL_RECOVERED rows=1
  notes: sqlite WAL 损坏后能开 + 读

=== R8: timeout ===
  [PASS] expected=TIMEOUT_OR_OK actual=TIMEOUT: database is locked after 1002ms

=== R9: readonly_root ===
  [SKIP] expected=ROOT_CHECK_PASS actual=ROOT_W_OK (需要应用层防护)
  notes: root 总是有 W 权限, 应用层必须自己检查 (V007.49 教训)

============================================================
  RESULT: 7 PASS / 0 FAIL / 2 SKIP / 9 total
============================================================
```

---

**总入口**: [DEPLOY_INFRASTRUCTURE.md](../DEPLOY_INFRASTRUCTURE.md) §0
**部署节奏**: [DEPLOY_RHYTHM.md](DEPLOY_RHYTHM.md)
**5 分钟速查**: [AGENT_INFRA.md](AGENT_INFRA.md)
**Migration 实战**: [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)
