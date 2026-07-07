# V007.32B — log_service v2 升级 + 找 server.log

> **作者**: dev-agent
> **日期**: 2026-07-07 18:35
> **状态**: 🚨 **P0 紧急** — 协调智能体执行 upgrade_log_service.sh

---

## 0. 现状 (v1 跑起来后实测)

| Endpoint | 状态 | 关键数据 |
|----------|------|---------|
| `/api/system` | ✅ OK | load 0.03, mem 14.3GB 空闲, disk 35.6GB 空闲, fd 372 |
| `/api/proc` | ✅ OK | server.py PID 26272 (15:23 启动, 314MB 内存), unified PID 26308 |
| `/api/db/health` | ✅ OK | db 96MB, wal 0, journal=wal, busy=5s, integ=ok, audit=117849 |
| `/api/dmesg` | ✅ OK | 看到 TCP SYN flood 8081 警告 |
| `/api/log?file=server.log` | ❌ FAIL | **No such file: /opt/app/deployments/meta/server.log** |

**关键问题**: v1 的 `_log` 强制 file 在 `LOG_DIR=/opt/app/deployments/meta`, 但 server.py 实际 cwd 是 `/opt/app/deployments/`, server.log 不在那!

---

## 1. 协调智能体 — 立即执行 upgrade_log_service.sh

### 完整命令 (在 yonaa 云控制台执行)

```bash
cd /tmp
# 复制 upgrade_log_service.sh 全部内容 (从 d:\filework\integration-worktree\upgrade_log_service.sh)
# 然后执行:
bash upgrade_log_service.sh
```

或者**手动一行一行执行** (如果复制文件失败):

```bash
# 1. 停 v1
pkill -f log_service.py
sleep 1

# 2. 写 v2 (升级版 log_service, 加 /api/find + 接受全路径)
# 从本地 d:\filework\integration-worktree\upgrade_log_service.sh 复制整个 cat > ... << LOG_SERVICE_EOF 块

# 3. 启动
nohup python3 /opt/app/deployments/log_service.py > /tmp/log_service.log 2>&1 &
sleep 2
cat /tmp/log_service.log

# 4. 验证
curl -s http://localhost:9101/api/system
curl -s 'http://localhost:9101/api/find?name=server.log&path=/opt/app'
curl -s 'http://localhost:9101/api/find?name=*.log&path=/opt/app/deployments'
curl -s 'http://localhost:9101/api/find?name=server*.py&path=/opt/app'
curl -s 'http://localhost:9101/api/find?name=architecture.db&path=/opt'
```

---

## 2. v2 升级点 (相比 v1)

| 升级 | 实现 |
|------|------|
| 接受**全路径** file | `if not fp.startswith('/'): fp = f'{LOG_DIR}/{fp}'` |
| 加 `/api/find` endpoint | `find {path} -name "{pat}" -type f` |
| 加 fd 计数 | 遍历 /proc/*/fd 统计系统 fd |
| 加 db 详细 | journal_mode / busy / integrity / wal size / shm size |
| 加 recent_disk_errors | 从 audit_logs 查最近 disk error |

---

## 3. 我已经实测的关键数据 (v1)

### yonaa 当前进程
| PID | 进程 | 启动 | 内存 |
|-----|------|------|------|
| 26272 | server.py | 15:23 | 314MB |
| 26308 | unified_server.py | 15:24 | 54MB |
| 7361 | log_service v1 | 18:28 | 12MB |

**server.py 已经跑了 3h5min, 没崩!** (跟我之前推测的"僵死"不同)

### yonaa db
| 字段 | 值 |
|------|------|
| size_mb | 96.04 |
| wal | 0 (没有积压) |
| journal | wal |
| busy_timeout | 5s |
| integrity | ok |
| audit_logs | 117849 (11.7万) |

### dmesg
- TCP SYN flood 警告 (8081 端口)
- psmouse VMMouse 频繁 lost sync (虚拟化鼠标, 正常)

---

## 4. 协调智能体 — Step 1: 升级 v2

**复制以下文件** → yonaa 云控制台 → 写入 `/tmp/upgrade_log_service.sh` → 执行:

```bash
bash /tmp/upgrade_log_service.sh
```

[upgrade_log_service.sh](file:///D:\filework\integration-worktree\upgrade_log_service.sh) 已在本地仓库 (完整可执行)。

---

## 5. 我立即做的 (v2 上线后)

| 步骤 | 动作 | URL |
|------|------|-----|
| 1 | 找 server.log 实际位置 | `/api/find?name=server.log&path=/` |
| 2 | 找所有 log 文件 | `/api/find?name=*.log&path=/` |
| 3 | 找 architecture.db 备份 | `/api/find?name=*.db*&path=/opt` |
| 4 | 找 server.py 启动脚本 | `/api/find?name=server*.py&path=/` |
| 5 | 读 server.log 找 30min 前真因 | `/api/log?file=/opt/.../server.log&lines=500&grep=disk` |
| 6 | 读所有相关 log | server.log, async.log, audit_retry.log |
| 7 | 写 V007.33 根因报告 | — |
| 8 | 实施 V007.29 P0 修复 | — |

---

## 6. 关键 — 协调智能体请立即回复

**Step 1 (升级 v2) 完成后**:
- 告诉我 "v2 启动, find 结果已看到"
- 我立即读 server.log 找根因

**或者** — 如果你发现 file=`/opt/.../server.log` 在 `find` 结果里, 立即告诉我路径, 我直接读 log!

---

## 7. 我已经发现的事实 (从 v1 实测)

1. ✅ yonaa 资源 OK (load 0.03, 内存 14.3GB 空闲, 磁盘 35.6GB 空闲, fd 372)
2. ✅ server.py 在跑 (PID 26272, 3h+ 没崩)
3. ✅ db OK (96MB, wal 0, integrity ok, 11.7万 audit_logs)
4. ❌ **server.log 不在预期路径** (需要找)
5. ⚠️ TCP SYN flood 8081 (可能是关键)

---

## 8. 修复路径 (预计 5h)

| 步骤 | 工作量 | 状态 |
|------|--------|------|
| 升级 v2 + 找 server.log | 5 min | 🚧 协调智能体执行 |
| 读 log + 找精确根因 | 15 min | 🚧 我做 |
| V007.29 P0 修复 (代码) | 3h | 🚧 我做 |
| 重新打包 + 部署 | 1h | 🚧 协调智能体 |
| 重启 server.py | 0.5h | 🚧 协调智能体 |
| 50 并发验证 | 0.5h | 🚧 我做 |

**总计 5h, 升级 v2 是第一步**。

---

## 9. Todo

| # | 任务 | 状态 |
|---|------|------|
| 1 | V007.21-V007.30 (10 个报告) | ✅ done |
| 2 | V007.31 (log_service 设计) | ✅ done |
| 3 | V007.32A (选项 A 部署手册) | ✅ done |
| 4 | V007.32B (升级 v2 + find log) | ✅ done |
| 5 | **v1 log_service 上线** | ✅ done (用户/协调智能体执行) |
| 6 | **升级 v2 + 找 server.log** | 🚧 **P0 紧急** |
| 7 | 读 log + V007.33 根因 | 🚧 待 |
| 8 | V007.29 P0 修复 | 🚧 待 |
| 9 | 50 并发验证 | 🚧 待 |