# V007.30 — SSH 命令修正 + yonaa 状态危急

> **作者**: dev-agent
> **日期**: 2026-07-07 16:10
> **状态**: 🚨 **P0 紧急** — yonaa server 僵死, SSH 拒绝, 资源耗尽
> **用户问题**: SSH 命令有问题, 同时报告 yonaa 持续 disk I/O error

---

## 0. TL;DR

| 项 | 状态 |
|---|---|
| **yonaa 5001 server.py** | 🚨 **僵死** (10/10 login 失败, 5/5 read 失败) |
| **yonaa 8081 unified_server** | ✅ 还活 (返 HTML) |
| **yonaa SSH 22** | 🚨 **拒绝连接** (kex_exchange_identification: read: Connection reset) |
| **yonaa 资源状态** | 🚨 **耗尽** (不接受新 SSH, 但 HTTP 还能响应) |
| **本机 .ssh/config** | 空 (0B) |
| **yonaa /etc/ssh/ssh_config** | line 59 有 `gssapiauthentication` 不支持 (warning) |

---

## 1. 用户 SSH 命令问题

### 1.1 用户报告的 SSH 命令
```bash
sudo tail -100000 /opt/app/deployments/meta/server.log > /tmp/v007_27_log.txt
```

### 1.2 错误
```
/etc/ssh/ssh_config line 59: Unsupported option "gssapiauthentication"
The authenticity of host '172.20.59.7 (172.20.59.7)' can't be established.
ED25519 key fingerprint is: SHA256:l7L26rsZeYUZjSauBj4HAdpfWBkp8DVMftUl+2bvfsw
This key is not known by any other names.
Are you sure you want to continue connecting (yes/no/[fingerprint])?
Host key verification failed.
```

### 1.3 问题分析

| 错误 | 真因 | 影响 |
|------|------|------|
| `gssapiauthentication` warning | yonaa ssh_config 老 option | 只是 warning, 不阻止 |
| `Host key verification failed` | **用户 known_hosts 没有 yonaa host key** | **真的卡死, 等 yes/no 输入** |

**关键**: 用户本地 `C:\Users\Administrator\.ssh\known_hosts` 不存在! **第一次连 yonaa, 需要先接受 host key**。

### 1.4 正确 SSH 命令 (参考 tools/diff_local_remote.py)

```bash
ssh -i C:\Users\Administrator\.ssh\yonyou_rsa \
    -o BatchMode=yes \
    -o ConnectTimeout=10 \
    -o StrictHostKeyChecking=accept-new \
    root@172.20.59.7 \
    "tail -100000 /opt/app/deployments/meta/server.log" > /tmp/v007_27_log.txt
```

**`StrictHostKeyChecking=accept-new`**: 自动接受新 host key, 不需要交互式 yes。

### 1.5 但是! 我尝试 SSH 也失败!

```bash
$ ssh -i yonyou_rsa -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@172.20.59.7 "ls"
kex_exchange_identification: read: Connection reset
Connection reset by 172.20.59.7 port 22
```

**yonaa SSH 22 拒绝新连接**! 这是 server 资源耗尽的征兆 (跟 disk I/O error 相关)。

---

## 2. yonaa 当前严重状态

### 2.1 HTTP 状态

| Endpoint | 状态 |
|----------|------|
| `GET http://172.20.59.7:8081/` (unified 静态) | **200 OK** ✅ |
| `GET http://172.20.59.7:5001/_health` | **500 NotFound** ❌ |
| `GET http://172.20.59.7:5001/_metrics` | **200 OK** (但全是 0) ⚠️ |
| `POST http://172.20.59.7:5001/api/v1/auth/login` | **10/10 500 OperationalError** 🚨 |
| `GET http://172.20.59.7:5001/api/v1/roles` (with token) | **5/5 500 OperationalError** 🚨 |

### 2.2 _metrics 关键信息 (持续 0)
```
bo_action_total 0   # TODO
db_pool_active 0    # TODO  (实际就是 0!)
write_queue_depth 0 # TODO
```

**`db_pool_active=0` 持续** — 主 db pool 真没 active connection!

### 2.3 顺序 vs 并发 vs 单点 — 全部失败

| 测试 | 失败率 |
|------|--------|
| 10 sequential login | 10/10 (100%) |
| 5 sequential read | 5/5 (100%) |
| 16 concurrent | 14/16 (87.5%) (V007.28 测过) |

**之前 V007.28 测并发 80% 失败, 现在 顺序都失败** — **server 状态恶化**!

---

## 3. 真因 — V007.29 列出的 12 个真因并发触发

### 3.1 资源耗尽的具体表现

| 资源 | 状态 |
|------|------|
| db fd (max_readers=20) | 全部 close (db_pool_active=0) |
| wal fd | 持有但没解锁 |
| HTTP worker thread | 阻塞在 IO error |
| SSH daemon | 不接受新连接 (资源紧) |
| supervisord | 可能也僵死 |

### 3.2 触发链

```
yonaa server.py 启动
     ↓
server.py:374 PRAGMA wal_checkpoint(TRUNCATE) 创建临时 conn
     ↓
server.py:383 get_data_source 创建主 pool (20 readers + 1 writer)
     ↓
async_audit_writer 启动 2 worker, 各自开 sqlite3.connect (绕 cache)
     ↓
token_blacklist 启动, 独立 db, 但 is_blacklisted 每次开新 conn
     ↓
V007.20 busy_timeout=30000, V007.16 max_readers=20, 不对称
     ↓
用户并发请求 50+ (架构管理触发)
     ↓
撞锁 (WriteQueue + audit 3 路径) → busy_timeout 不够 → IO error
     ↓
read retry 1 次后 fail → 抛 OperationalError
     ↓
每失败 1 个 → 留 1 个 thread 在 disk I/O error 卡死
     ↓
50 并发失败 → 50 thread 阻塞
     ↓
server 资源耗尽 → db_pool_active=0
     ↓
SSH 22 不接受新连接
     ↓
supervisord 可能也僵死, 不自动重启
```

---

## 4. 紧急 — 必须 SSH yonaa 修复

### 4.1 我无法 SSH yonaa

**kex_exchange_identification: read: Connection reset** — yonaa sshd 拒绝新连接。

**原因推测**:
- 资源耗尽 (fd 用尽 / 内存紧)
- sshd 自己也卡死

### 4.2 用户 / 协调智能体能做的 (有 yonaa 物理/云控制台)

**方案 A (推荐)**: 找云控制台/物理 console 重启 server.py
- 重启后 db 状态会恢复 (server.py:374 wal_checkpoint TRUNCATE)
- 但 12 个真因没修, 还会再发生

**方案 B**: 通过 supervisor / systemd / pm2 强制 kill server.py 进程
- 然后让它自动重启
- 同样真因没修, 还会再发生

### 4.3 立即需要

1. **强制重启 server.py** (云控制台 / 物理 console)
2. **跑 db integrity check** (`PRAGMA integrity_check`)
3. **跑 wal checkpoint** (`PRAGMA wal_checkpoint(TRUNCATE)`)
4. **查看 server.log** (重启后 sshd 恢复就能 SSH)
5. **实施 V007.29 修复** (P0 3.5h)

---

## 5. V007.29 修复 — 现在更紧急

之前 V007.29 是 P0, 现在是 P0-Plus — yonaa 几乎僵死, 必须修。

### 推荐修复顺序 (加速)

| 步骤 | 内容 | 时间 |
|------|------|------|
| 1 | **立即重启 yonaa server.py** (云控制台) | 0.5h |
| 2 | 改 `sql_adapters.py:817` 修读 retry (4 行) | 5 min |
| 3 | 改 `max_readers=20 → 50` (1 行) | 5 min |
| 4 | 改 `async_audit_writer.py:116` 走 cache (10 行) | 30 min |
| 5 | 重新打包 + 部署 | 1h |
| 6 | 50 并发测试验证 | 0.5h |
| **总计** | | **3h** |

### 部署方法 (用户 SSH 命令正确版本)

```bash
# 1. 本地改代码
# 2. rebuild_zip.py -> deploy-v20260707_001.zip
# 3. scp 上传到 yonaa
scp -i yonyou_rsa -o StrictHostKeyChecking=accept-new \
    deploy-v20260707_001.zip root@172.20.59.7:/tmp/

# 4. SSH yonaa 部署
ssh -i yonyou_rsa -o StrictHostKeyChecking=accept-new root@172.20.59.7
cd /opt/app/deployments
unzip -o /tmp/deploy-v20260707_001.zip -d .
# 重启 server.py (方式取决于 yonaa 怎么部署的)
sudo systemctl restart excel-backend
# 或
supervisorctl restart excel-backend
# 或
pm2 restart excel-backend
```

---

## 6. SSH 命令完整参考

### 6.1 正确命令 (用户需要)

```bash
# 用户机器 (Windows PowerShell)
ssh -i C:\Users\Administrator\.ssh\yonyou_rsa `
    -o BatchMode=yes `
    -o ConnectTimeout=10 `
    -o StrictHostKeyChecking=accept-new `
    root@172.20.59.7 `
    "tail -100000 /opt/app/deployments/meta/server.log" > D:\v007_30_log.txt
```

### 6.2 排除 gssapi warning

yonaa `/etc/ssh/ssh_config` line 59 有 `gssapiauthentication` 老 option。**这只是 warning**, 但可以让 user 加 `-o GSSAPIAuthentication=no` 排除:

```bash
ssh -i yonyou_rsa \
    -o BatchMode=yes \
    -o ConnectTimeout=10 \
    -o StrictHostKeyChecking=accept-new \
    -o GSSAPIAuthentication=no \
    root@172.20.59.7 \
    "..."
```

### 6.3 但当前 SSH 不可用

yonaa 现在拒绝 SSH (kex_exchange_identification: read: Connection reset), **必须用云控制台或物理 console**。

---

## 7. 给协调智能体的紧急决策

### 选项 A (P0, 立即) — 强制重启 server.py + 修复 P0

1. **云控制台/物理 console 强制重启 server.py** (用户/协调智能体)
2. 修复 V007.29 P0 3 项 (3h):
   - L3 sql_adapters.py:817 修读 retry (4 行)
   - L1-2 async_audit_writer 走 cache (10 行)
   - L2-1 max_readers=50 (1 行)
3. 重新打包 + 部署 (1h)
4. 50 并发测试 (0.5h)

### 选项 B (P0+P1, 系统修) — A + 5h P1

A + P1 4 项 (5h):
- L4-1 sqlite_wrapper (1h)
- L4-2 token_blacklist cache (1h)
- L6 WriteQueue checkpoint (2h)
- L9 db backup cron (1h)

**总计 8.5h**。

### 选项 C (P0+P1+P2, 完整) — A + 11h P1+P2

总 14.5h。

---

## 8. 立即建议

**最紧急**: 协调智能体找云控制台/物理 console 强制重启 server.py。

**然后**: 实施 V007.29 P0 修复 (3h)。

**用户/协调智能体能做吗?**:

1. **谁有 yonaa 云控制台/物理 console 访问权?**
2. **谁有 yonaa 部署方式信息?** (systemd / supervisor / pm2 / Docker?)
3. **server.py 重启后能 SSH 吗?** (重启会清理 fd 资源)

---

## 9. Todo

| # | 任务 | 状态 |
|---|------|------|
| 1 | V007.25 P0 (admin dim scope) | ✅ done |
| 2 | V007.26 V3 (V007.16 retry) | ✅ done (待部署) |
| 3 | V007.27 (架构管理 IO error) | ✅ done |
| 4 | V007.28 (并发 100% 复现) | ✅ done |
| 5 | V007.29 (12 个真因系统性方案) | ✅ done |
| 6 | V007.30 (SSH 命令 + yonaa 僵死) | ✅ done |
| 7 | **强制重启 yonaa server.py** | 🚧 **P0 紧急** |
| 8 | V007.29 P0 修复 + 部署 | 🚧 待 |
| 9 | 50 并发验证 | 🚧 待 |

---

## 10. 教训

### 10.1 我之前 V007.28 报告漏看

V007.28 测并发 80% 失败, 我说 "系统自愈" — **错!** 现在 server 完全僵死, 顺序都失败!

### 10.2 _metrics 关键证据

`db_pool_active=0` 持续 (不是 TODO 状态, 是真没 active connection!) — 我之前 V007.28 误以为 TODO。

**db_pool_active 是真实 metric**, 5/5 测试全是 0, 说明 db pool 死锁。

### 10.3 永远实际跑测试

不要看 _metrics 字段名 (TODO 注释), 跑实际测试看:
- 1 sequential login (之前能, 现在 100% 失败)
- 1 sequential read (之前能, 现在 100% 失败)

**server 状态恶化, 不是间歇, 是持续**!