# 打包部署交接文档 V007.52 - 元能力基础设施 (core_service v1.1)

> 生成时间: 2026-07-11 | 源分支: release/pre-2026-06-29 | 涉及 commits: 17c4bb6, b60644b

---

## 一、版本概述

本版本建立**元能力基础设施** —— 一个独立的"元服务" `core_service` (端口 9200)，让运维无需 SSH 即可远程管理 yonaa 上的所有业务服务。同时修复了 `log_service` supervisor pid 误判 bug 和 `smart_deploy.sh` log_service 永远不重启的 bug。

### 核心特性

| 组件 | 版本 | 说明 |
|------|------|------|
| `core_service.py` | **v1.1** | 极简元能力服务 (3 端点, 永不自杀) |
| `core_service_watchdog.sh` | v1.0 | cron 守护 (每分钟检查 9200) |
| `restart_all.sh` | v1.0 | 一键重启 4 个核心服务 |
| `log_service.py` | **v4.10** | 修复 supervisor pid 误判 |
| `smart_deploy.sh` | **V007.49** | 修复 Step 7 log_service 永远不重启 |
| `e2e_core_service.py` | v1.0 | 16 case 端到端测试 (PASS=16) |

---

## 二、设计动机 —— 为什么需要 core_service

### 2.1 旧痛点

1. **每次更新 log_service 必须 SSH**：登录服务器 → 备份 → cp → 重启 → 验证
2. **SSH 不通就无法管理**：网络抖动、sshd 挂了、密钥过期都致命
3. **log_service v1.0 的 `/api/service/restart` 杀死 core_service**：因为 `pkill -9 -f python` 匹配所有 python 进程
4. **smart_deploy.sh 的 Step 7 不重启 log_service**：`ss -tlnp | grep :9101` 永远找到旧进程

### 2.2 解决思路

**分离关注点**：把"上传+执行"作为**最底层稳定元能力**，业务服务的启停由调用方决定：

```
┌─────────────────────────────────────────────────────────┐
│ yonaa 基础设施架构                                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  core_service (9200) ← 元能力 (永不自杀)                │
│     ├─ /api/upload     POST 上传文件                    │
│     ├─ /api/exec       GET  执行任意白名单命令          │
│     └─ /api            GET  元信息                      │
│                                                         │
│  log_service (9101) ← 监控服务 (有 watchdog + supervisor) │
│     ├─ 32 个业务端点 (含 P1: supervisor/archive/forecast)│
│     └─ /api/service/supervisor?action=restart 可以重启  │
│                                                         │
│  backend (3011)    ← Flask API (v007.46)               │
│  frontend (8081)   ← 静态文件 (unified v004)           │
│                                                         │
│  cron → core_service_watchdog.sh 每分钟检查 9200        │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**核心原则**：
- core_service 永远只做上传和执行，**不做启停**（避开 pkill 误杀）
- 调用方负责完整生命周期：`exec pkill → exec bash start_xxx.sh`
- 所有启动脚本放在 `/opt/app/shared/start_*.sh`，方便复用

---

## 三、core_service v1.1 设计

### 3.1 文件位置

- 本机: `d:\filework\release-prep-worktree\tools\core_service.py` (243 行)
- yonaa: `/opt/app/shared/core_service.py` (v1.0 备份在 `/opt/app/shared/core_service.py.v1.0.bak`)
- deploy_bundle: `deploy_bundle/tools/core_service.py`

### 3.2 端点设计 (只有 3 个)

| 端点 | 方法 | 功能 | 鉴权 |
|------|------|------|------|
| `/api` | GET | 服务元信息 + 使用文档 | 无 |
| `/api/upload` | POST | 上传文件 (raw bytes, max 500MB) | token |
| `/api/exec` | GET | 执行命令 (白名单, bg=true 后台) | token |

### 3.3 配置常量

```python
VERSION         = "v1.1"
PORT            = 9200
SECRET          = "v007.52-core"          # token 密钥
TOKEN_HR        = 8                       # token 8 小时有效
MAX_UPLOAD_MB   = 500                     # 单文件最大 500MB
```

### 3.4 4 层安全防护

| 层级 | 机制 | 实现 |
|------|------|------|
| 1 | Token 鉴权 | SHA256(secret:hour)[:16], 8h 有效 |
| 2 | 路径白名单 | `/opt/app/{deployments,shared,backups}`, `/tmp`, `/var/log` |
| 3 | 命令白名单 | 56 个基础命令 (ls/cat/bash/python3/pkill/pgrep/unzip/nohup 等) |
| 4 | 黑名单 | `rm -rf /`, `dd if=`, `mkfs.`, `shutdown`, `reboot` 等 |

### 3.5 Rate Limit

20 req/s per IP (token bucket), 超过返回 429。

### 3.6 Token 计算方法

```python
import hashlib, time
SECRET = "v007.52-core"
hour = int(time.time()) // 3600
token = hashlib.sha256(f"{SECRET}:{hour}".encode()).hexdigest()[:16]
```

token 在 `hour` 和 `hour-8` 之间都有效（容忍 ±8h 时钟漂移）。

### 3.7 关键 bug 修复（v1.0 → v1.1）

| Bug | 原因 | 修复 |
|-----|------|------|
| `/api/service/restart` 杀死 core_service | `pkill -9 -f python` 匹配所有 python 进程 | 删除所有 `/api/service/*` 端点 |
| Popen 影响 core_service 自身 | 进程隔离不彻底 | _start_service 不 Popen，只写脚本文件 |
| pgrep `cmd0="python"` 误匹配 | 首词匹配太宽 | 用完整 cmd 字符串 + 排除 self |

---

## 四、log_service v4.10 bug 修复

### 4.1 Bug 描述

v4.9 的 `/api/service/supervisor?action=status` 返回：

```json
{
  "name": "unified",
  "pid": "9668",          // 错误! 这是 core_service 的 PID
  "all_pids": ["9668", "10169", "10908"]
}
```

### 4.2 根因

`pgrep -f svc["cmd"].split()[0]` 使用了**首词**（`python3` 或 `/opt/miniconda3-py39/bin/python`），匹配所有 python 进程，包括 core_service。

### 4.3 修复

```python
# 修改前
proc = subprocess.run(["pgrep", "-f", svc["cmd"].split()[0]], ...)
pids = [p for p in proc.stdout.strip().split("\n") if p.isdigit()]

# 修改后 (V007.52 BUG-FIX)
my_pid = str(os.getpid())
cmd_pattern = svc["cmd"]                          # 完整 cmd 字符串
proc = subprocess.run(["pgrep", "-f", cmd_pattern], ...)
pids = [p for p in proc.stdout.strip().split("\n") if p.isdigit()]
pids = [p for p in pids if p != my_pid]            # 排除 log_service 自己
# 注: core_service 的 cmd 不含 "server" / "unified" / "log_service",
#     完整 cmd 匹配天然不会命中 core_service
```

### 4.4 修复验证

| 字段 | v4.9 (bug) | v4.10 (fixed) |
|------|-----------|---------------|
| meta_server.pid | 10246 ✓ | 10246 ✓ |
| unified.pid | **9668 ✗** (core_service) | **10169 ✓** (真实 unified_server) |

---

## 五、smart_deploy.sh Step 7 bug 修复

### 5.1 Bug 描述

每次部署后，`smart_deploy.sh` 完成其他步骤但**不重启 log_service**，导致新代码永远不加载。

### 5.2 根因

```bash
# 修改前 (永远不重启)
if ss -tlnp | grep -q :9101; then
    echo "[INFO] log_service already running, skipping restart"
fi
```

`ss -tlnp | grep :9101` 永远找到旧进程 listening，新代码永远不重启。

### 5.3 修复

```bash
# 修改后 (V007.49 P1 BUG-FIX)
EXISTING_PID=$(pgrep -f "log_service.py" | head -1)
if [ -n "$EXISTING_PID" ]; then
    echo "  [INFO] 杀旧 log_service PID=$EXISTING_PID"
    kill -9 $EXISTING_PID 2>/dev/null
    sleep 2
fi
# 同步新代码 (从 zip extract path 复制到 /tmp/deploy_bundle/tools/)
cp /tmp/deploy_bundle/tools/log_service.py /tmp/deploy_bundle/tools/log_service.py.new
cat /tmp/deploy_bundle/tools/log_service.py.new > /tmp/deploy_bundle/tools/log_service.py
# 启动新版本
setsid nohup /usr/bin/python3 /tmp/deploy_bundle/tools/log_service.py >> /var/log/log_service.log 2>&1 < /dev/null &
disown
```

---

## 六、yonaa 部署清单

### 6.1 服务配置

| 服务 | 端口 | 启动脚本 | 日志路径 |
|------|------|---------|---------|
| core_service | 9200 | `/opt/app/shared/start_core.sh` | `/var/log/core_service.log` |
| log_service | 9101 | `/opt/app/shared/start_log.sh` | `/var/log/log_service.log` |
| backend | 3011 | `/opt/app/shared/start_server.sh` | `/var/log/server.log` |
| frontend | 8081 | `/opt/app/shared/start_backend.sh` | `/var/log/unified.log` |

### 6.2 守护机制

**双保险**：
- core_service 自带 cron watchdog（每分钟检查 9200）
- log_service 自带 supervisor（`/api/service/supervisor?action=restart`）

### 6.3 备份保留

| 文件 | 内容 |
|------|------|
| `/tmp/deploy_bundle/tools/log_service.v4.8.py.bak` | v4.8 |
| `/tmp/deploy_bundle/tools/log_service.v4.9.py.bak` | v4.9 |
| `/tmp/log_service_v4.9.py` | v4.9 |
| `/tmp/log_service_v4.10.py` | v4.10 |
| `/tmp/core_service_v1.1.py` | core_service v1.1 |
| `/opt/app/shared/core_service.py.v1.0.bak` | core_service v1.0 旧版 |

### 6.4 Cron 配置

```
* * * * * /opt/app/shared/core_service_watchdog.sh # core_service watchdog every 1min
```

---

## 七、核心脚本清单

### 7.1 start_core.sh

```bash
#!/bin/bash
pkill -9 -f core_service.py 2>/dev/null
sleep 2
cd /opt/app/shared
setsid nohup /usr/bin/python3 /opt/app/shared/core_service.py >> /var/log/core_service.log 2>&1 < /dev/null &
PID=$!
disown $PID 2>/dev/null
echo "launched PID=$PID"
```

### 7.2 core_service_watchdog.sh

每分钟执行：
1. `curl --max-time 3 http://127.0.0.1:9200/api`
2. 失败 → pkill core_service → bash start_core.sh → 验证
3. 成功 → exit 0

日志：`/var/log/core_service_watchdog.log`

### 7.3 restart_all.sh

按依赖顺序拉起：core_service → log_service → backend → frontend

### 7.4 start_log.sh / start_server.sh / start_backend.sh

结构相同：pkill → sleep → setsid+nohup → disown

---

## 八、API 用法

### 8.1 生成 token

```python
import hashlib, time
SECRET = "v007.52-core"
hour = int(time.time()) // 3600
token = hashlib.sha256(f"{SECRET}:{hour}".encode()).hexdigest()[:16]
# 例: fa0fc564cbb388db
```

### 8.2 上传文件

```bash
# 注意: 用 --data-binary @文件路径, 不要用 --data-binary "$bytes" (会被二次编码)
curl -X POST "http://172.20.59.7:9200/api/upload?path=/tmp/xxx.py&token=$TOKEN" \
     -H "Content-Type: application/octet-stream" \
     --data-binary "@local_file.py"
```

**避坑指南**：
- PowerShell 用 `[byte[]]` 传给 `--data-binary` 会二次编码为 ASCII 字符串
- 正确做法：先写本地临时文件，再用 `--data-binary @file`
- 或用 Python `requests.post(url, data=open(file, 'rb').read())`

### 8.3 远程写脚本文件 (避免 upload 编码问题)

当需要上传 shell 脚本时，先 base64 编码，再通过 exec 写入：

```bash
# 本机生成 base64
$script = @'
#!/bin/bash
echo "hello"
'@
$b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($script))

# 通过 exec 写入
curl -G "http://172.20.59.7:9200/api/exec" \
     --data-urlencode "cmd=echo $b64 | base64 -d > /opt/app/shared/start_xxx.sh && chmod +x /opt/app/shared/start_xxx.sh" \
     --data-urlencode "token=$TOKEN"
```

### 8.4 执行命令

```bash
# 同步执行 (默认 timeout 30s, max 120s)
curl -G "http://172.20.59.7:9200/api/exec" \
     --data-urlencode "cmd=ls /opt/app/shared/" \
     --data-urlencode "token=$TOKEN"

# 后台执行 (返回 pid, 进程独立于 exec 父进程)
curl -G "http://172.20.59.7:9200/api/exec" \
     --data-urlencode "cmd=bash /opt/app/shared/start_log.sh" \
     --data-urlencode "bg=true" \
     --data-urlencode "token=$TOKEN"
```

### 8.5 启停服务 (调用方决定生命周期)

```bash
# 停 log_service
curl -G "http://172.20.59.7:9200/api/exec" \
     --data-urlencode "cmd=pkill -f log_service.py" \
     --data-urlencode "token=$TOKEN"

# 启 log_service (用 start_*.sh 确保 setsid+nohup)
curl -G "http://172.20.59.7:9200/api/exec" \
     --data-urlencode "cmd=bash /opt/app/shared/start_log.sh" \
     --data-urlencode "bg=true" \
     --data-urlencode "token=$TOKEN"
```

### 8.6 一键重启全部

```bash
curl -G "http://172.20.59.7:9200/api/exec" \
     --data-urlencode "cmd=bash /opt/app/shared/restart_all.sh" \
     --data-urlencode "bg=true" \
     --data-urlencode "token=$TOKEN"
```

---

## 九、E2E 测试覆盖 (e2e_core_service.py)

**16 个测试全部通过** (commit b60644b)：

| # | 测试组 | 通过 |
|---|--------|------|
| 1 | /api 元信息 (version + endpoints) | 3 |
| 2 | 无 token 拒绝 (upload + exec) | 2 |
| 3 | upload + size 校验 | 2 |
| 4 | exec 同步 + 内容匹配 | 2 |
| 5 | exec bg=true + PID | 2 |
| 6 | 路径白名单 (/etc/passwd) | 1 |
| 7 | 命令白名单 (未知命令) | 1 |
| 8 | 黑名单 (rm -rf + shutdown) | 2 |
| 9 | 限流 (20 req/s, 25 req → 10 ok + 15 blocked) | 1 |
| **合计** | | **16/16** |

**运行方法**：
```bash
cd d:\filework\release-prep-worktree
python tools/e2e_core_service.py
```

---

## 十、Watchdog 真实触发验证 (2026-07-11)

**事件时间线**：
| 时间 | 事件 |
|------|------|
| 20:56:xx | 手动 `kill -9 11240` (core_service PID) |
| 20:57:01 | cron watchdog 检测到 9200 死, 启动 start_core.sh |
| 20:57:08 | 新 core_service PID 11681 起来, 验证 OK |

**响应时间：7 秒**（远小于 60s cron 间隔）。

**watchdog log**:
```
2026-07-11 20:57:01 [WARN] core_service not responding on 9200, restarting...
launched PID=11681
2026-07-11 20:57:08 [OK] core_service restarted successfully
```

---

## 十一、未来改进 (P2)

1. **HTTPS 支持**：core_service 目前是 HTTP，可加 TLS
2. **细粒度 token**：不同 token 对应不同权限（只读 / 写文件 / 执行）
3. **审计日志**：所有 upload/exec 调用记录到 `/var/log/core_service_audit.log`
4. **systemd unit**：除 cron 外加 systemd 双保险
5. **批量上传**：当前一次只传一个文件，POST body 多文件 part 支持

---

## 十二、回滚方案

如需回滚到 v007.51 状态：

```bash
# 1. 恢复 core_service v1.0
ssh root@172.20.59.7
cp /opt/app/shared/core_service.py.v1.0.bak /opt/app/shared/core_service.py
pkill -9 -f core_service.py
sleep 2
bash /opt/app/shared/start_core.sh

# 2. 恢复 log_service v4.8
cp /tmp/deploy_bundle/tools/log_service.v4.8.py.bak /tmp/deploy_bundle/tools/log_service.py
bash /opt/app/shared/start_log.sh &

# 3. 卸载 watchdog
crontab -l | grep -v core_service_watchdog | crontab -

# 4. 验证
curl http://127.0.0.1:9200/api  # 应该看到 8 个端点 (v1.0)
curl http://127.0.0.1:9101/api  # 应该看到 v4.8 (27 个端点)
```

---

## 十三、关键 commit

| Hash | 标题 |
|------|------|
| `17c4bb6` | feat: core_service v1.1 + log_service v4.10 + smart_deploy bug fix |
| `b60644b` | test: e2e_core_service.py - 16 case 端到端测试 |

---

## 十四、变更文件清单

| 文件 | 类型 | 改动 |
|------|------|------|
| `tools/core_service.py` | 新增 | v1.1 元能力服务 (243 行) |
| `deploy_bundle/tools/core_service.py` | 新增 | 同上 (部署包) |
| `deploy_bundle/tools/core_service.service` | 新增 | systemd unit (备用) |
| `deploy_bundle/tools/core_service_watchdog.sh` | 新增 | cron 守护 |
| `tools/log_service.py` | 修改 | v4.9 → v4.10 (supervisor pid 修复) |
| `deploy_bundle/tools/log_service.py` | 修改 | 同上 |
| `tools/smart_deploy.sh` | 修改 | Step 7 重启 log_service |
| `deploy_bundle/tools/smart_deploy.sh` | 修改 | 同上 |
| `tools/remote_monitor.ps1` | 修改 | 增强 |
| `tools/e2e_core_service.py` | 新增 | 16 case 端到端测试 |

---

## 十五、维护要点

1. **修改 core_service.py 后**：必须用 `--data-binary @file` 上传 (避免 PowerShell 编码 bug)
2. **新加启动脚本**：用 base64 写文件，再 chmod +x (避免 upload 编码 bug)
3. **token 续期**：每小时自然续，8h 漂移容忍，无需手动刷新
4. **watchdog 自检**：看 `/var/log/core_service_watchdog.log`
5. **service 状态**：core_service 不会列出其他服务，直接 `ss -tlnp | grep -E ':(3011|8081|9101|9200) '`

---

> 文档维护: V007.52 元能力建立后写
> 后续改动请同步更新本文件