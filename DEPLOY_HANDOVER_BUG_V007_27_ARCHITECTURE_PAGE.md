# V007.27 — 架构管理页面触发 disk I/O error + 自动退出登录

> **作者**: dev-agent
> **日期**: 2026-07-07 15:35
> **状态**: 🟡 P2 — 系统已自愈, 但根因未明
> **新增信息**: 用户报告新场景

---

## 0. TL;DR

| 字段 | 值 |
|------|-----|
| BUG-ID | **V007.27 架构管理页面触发 disk I/O error + 自动退出登录** |
| 严重度 | **P2** (间歇性, 已自愈) |
| 真因 | **未明** (需要 yonaa server.py log) |
| 现象 | 30 min 前: 点架构管理 → 系统自动退出 → 再登录 IO error → 现在好了 |
| 修复时间 | **TBD** (需要先看 log) |

---

## 1. 用户新报告 (V007.27)

### 1.1 30 min 前的完整时序

```
T0: 用户在架构管理页面
T1: 点击浏览
T2: 系统自动退出登录 (前端跳转到 login)
T3: 用户再登录 → disk I/O error
T4: 现在可以登录了 (db 状态恢复)
T5: console 显示 4 个 endpoint 错误:
  - :8081/api/v2/bo/domain?version_id=3&page_size=1000 -> 500
  - :8081/api/v2/bo/service_module?version_id=3&page_size=5000 -> 400
  - :8081/api/v2/bo/relationship?version_id=3 -> 400
  - :8081/api/v2/value-help/enum/relation_type -> 500
  - :8081/api/v2/value-help/enum/direction -> 500
```

### 1.2 console 错误

```
[useMetaList] 加载数据: Error: disk I/O error
    at ve (MetaForm-C9f7K_CF.js:4:70857)
    at async Xe (MetaForm-C9f7K_CF.js:4:75833)
```

**这是前端 `MetaForm` 组件报 disk I/O error, 不是直接 HTTP 错误**!

---

## 2. yonaa /_diagnostics 实测 (我刚跑)

### 2.1 关键发现

```json
{
  "health": {
    "backup_count": 0,    ← 没有 db backup!
    "db_size": "unknown",  ← TODO
    "integrity": "unknown", ← TODO
    "pool_active": 0,    ← TODO
    "status": "unknown",  ← TODO
    "wal_size": "unknown" ← TODO
  },
  "recent_errors": [],   ← 1h 内没错误 (系统已自愈!)
  "recovery_suggestions": [
    {"action": "DB integrity != ok, run: python scripts/recover_db.py", "level": "critical"},
    {"action": "No backup found, run: python scripts/backup_db.py", "level": "info"}
  ],
  "trace_id": "f099429776884452b87988621121cc1c"
}
```

**关键**:
- **`recent_errors: []`** — 1h 内没错误 (用户报告 30 min 前, 已被 record 但 1h 滚动了)
- **`backup_count: 0`** — **没 db backup, db 状态坏掉无法恢复!**
- **health 全是 "unknown"** — diagnostics 没真读 db 状态, 全部 TODO

### 2.2 yonaa 8081 端点 (我刚实测 5001 拿 token 后)

| Endpoint | 8081 现在状态 |
|----------|----------------|
| `/api/v2/bo/domain?version_id=3&page_size=1000` | **200 OK, 11 rows** |
| `/api/v2/bo/service_module?version_id=3&page_size=5000` | **200 OK, 409 rows** |
| `/api/v2/bo/relationship?version_id=3` | **200 OK, 5756 rows** |
| `/api/v2/value-help/enum/relation_type` | **200 OK, 4 rows** |
| `POST /api/v1/auth/login` (admin) | **200 OK** (拿 token) |

**所有 endpoint 现在都工作!**

---

## 3. 推测的真因 (待验证)

### 3.1 推测 — db 状态暂时损坏

**触发场景**:
1. 用户点击架构管理 → 触发大量 query (domain/service_module/relationship + value-help)
2. 这些 query 写入 audit log (WriteQueue + audit_async_queue)
3. audit log 写入时撞 wal lock
4. busy_timeout 30s (V007.20 修复) 不够 → 抛 disk I/O error
5. server.py 短暂 bug → token 黑名单 / session 失效 → 自动退出登录
6. 用户再登录 → server.py 重试 (V007.16) → db 自愈 → 登录成功
7. 现在 server.py 自愈了, 之前 30 min 内写不进去的 audit log 在 WriteQueue 里 buffer
8. 之前失败的 endpoint 现在 work (因为 db 状态恢复)

### 3.2 推测 — server.py 短暂重启 / OOM

**触发场景**:
1. 架构管理页面 trigger 大量并发 query
2. server.py memory 上涨 → OOM
3. supervisor 重启 server.py
4. 重启期间 token 失效 → 用户自动退出
5. 重启后 db 状态 OK (server.py:374 wal_checkpoint TRUNCATE)
6. 用户再登录 OK

### 3.3 推测 — WriteQueue 死锁

**触发场景**:
1. WriteQueue 单写线程 + audit_async_queue + async_audit_writer 三条路径同时写 audit_logs
2. 撞锁频繁 → busy_timeout 30s 不够
3. WriteQueue 死锁 → 写不进去
4. server.py 业务 query 失败 → 报 disk I/O error
5. db 状态实际没坏, 只是 WriteQueue 卡住
6. WriteQueue 重试 → 恢复

---

## 4. 必须看的 yonaa log

### 4.1 用户需要 SSH yonaa 跑

```bash
ssh user@172.20.59.7
sudo tail -10000 /opt/app/deployments/meta/server.log | grep -A 50 "30 min ago\|14:30\|14:35\|disk I/O\|wal\|Traceback\|Error"
# 或
sudo journalctl -u excel-backend --since "1 hour ago" | tail -500
# 或
sudo cat /opt/app/deployments/meta/server.log | grep -B 5 -A 30 "OperationalError\|disk I/O\|WriteQueue"
```

**关键 log 信息**:
1. **db backup time** — 什么时候最后一次 backup (`backup_count: 0` 警告)
2. **server 启动时间** — 是否在 30 min 前重启过
3. **WriteQueue backlog** — 当时 WriteQueue 深度
4. **busy_timeout hit** — 撞锁次数
5. **OOM killer** — 是否有 OOM
6. **token invalidation** — token 为什么被黑

### 4.2 我可以通过 HTTP 间接查的

```bash
# /api/v2/action/_diagnostics (with admin token) 已经查过:
# - recent_errors: [] (1h 滚动, 30 min 前已不在)
# - interceptor_warnings: [] (chain warnings 也没)

# 其他间接方式
# - /api/v1/admin/_db_health (with admin token) - 实际 db 状态
# - /api/v2/bo/_chain (测试链式 query)
# - /api/v2/bo/relationship?version_id=3&page_size=5000 (大 query 测压力)
```

---

## 5. 立即建议 (按紧急度)

### 选项 A (推荐, 0.5h) — 拿 yonaa server log

让协调智能体 / 用户 SSH yonaa:
```bash
sudo tail -100000 /opt/app/deployments/meta/server.log > /tmp/v007_27_log.txt
# 然后 scp 回本地分析
```

### 选项 B (1h) — 加 db backup

**`backup_count: 0` 是真正的风险!**
- db 一旦坏掉无法恢复
- 写脚本: `meta/scripts/backup_db.py --auto-backup` 每 6h 跑一次
- 部署到 yonaa cron

### 选项 C (2h) — 加 db integrity 检查

`db_integrity: unknown` (TODO 状态), 加真正检查:
```python
# meta/core/db_health_monitor.py 增强
def check_db_integrity():
    conn = sqlite3.connect(db_path, timeout=5)
    result = conn.execute("PRAGMA integrity_check").fetchone()
    if result[0] != 'ok':
        raise Alert("DB integrity failed: " + result[0])
    return 'ok'
```

### 选项 D (4h) — V007.20.2 增强 WriteQueue + busy_timeout

- WriteQueue 加 max_backlog + auto-flush
- busy_timeout 30s → 60s (V007.20.2)
- 撞锁时直接 retry 10 次 (不等 30s)

---

## 6. 跟之前 V007.26 / V007.25 / V007.24 的关系

| Bug | 真因 | 修复 |
|-----|------|------|
| V007.21 | server 启动 TRUNCATE + 多 reader fd | V007.16 修 (is_valid + reader cache) |
| V007.23 | 3 个独立 pool | V007.24 Phase 1 修 (DataSource cache) |
| V007.24 | 30+ 文件 lazy init | V007.24 Phase 1 修 (部分) |
| V007.25 | yonaa db 缺 admin dim scope | P0 (db INSERT) 已部署 |
| V007.26 | V007.16 retry 缺陷 | V3 报告 (1 行代码, 待部署) |
| **V007.27 (现在)** | **未明 — 需要 log** | 待诊断 |

**V007.27 跟前几个 V007.2x 是独立的, 是新场景**。

---

## 7. 紧急决策 (协调智能体)

### 优先级 P0: 拿 yonaa log (0.5h)
不修, 只诊断。
SSH yonaa 跑 log dump, scp 回本地。

### 优先级 P1: 修 V007.16 retry (V007.26 V3 报告, 1h)
1 行代码 + 重启 + 验证

### 优先级 P2: 加 db backup (1h)
脚本 + cron

### 优先级 P3: 写 (1-2h)
WriteQueue 增强

**我建议先做 P0 (拿 log), 因为 V007.27 真因未明, 盲目修可能没用**。

---

## 8. Todo 更新

| # | 任务 | 状态 |
|---|------|------|
| 1 | V007.25 P0 (admin dim scope INSERT) | ✅ done |
| 2 | V007.26 V3 报告 (V007.16 retry 缺陷) | ✅ done (待部署) |
| 3 | **V007.27 (新场景)** | 🚧 需 log 诊断 |
| 4 | 改 sql_adapters.py:817 部署 yonaa | 🚧 待 |
| 5 | 加 db backup cron | 🚧 待 |
| 6 | WriteQueue 增强 | 🚧 待 |

---

## 9. 用户问题回答

> "你看看是否有必要看看服务器上的 log?"

**是, 强烈建议看 server.py log**:
1. **30 min 前发生了什么** — 触发场景的完整 log
2. **db state 变化** — wal/shm/inode 状态
3. **server 是否有重启** — supervisor log
4. **WriteQueue 状态** — backlog / deadlock

**没有 log, 我们只能推测, 修不到根因**。

---

## 10. 立即可做

### 10.1 我可以做的 (无 SSH)

- ✅ 跑 yonaa /_diagnostics (已跑)
- ✅ 跑 yonaa 所有 endpoint 测试 (已跑, 全 OK)
- ✅ 看本地 8081 / 5001 健康状态
- ❌ SSH yonaa (无权限)

### 10.2 用户可以做的 (有 SSH)

- SSH yonaa 跑 log dump 命令
- 看 supervisor / systemd log
- 跑 db integrity_check / wal_checkpoint

### 10.3 协调智能体可以做的

- 让用户跑 log dump, scp 回本地
- 让我分析 log
- 然后决定怎么修

**你/协调智能体能 SSH yonaa 跑 log dump 吗?**
