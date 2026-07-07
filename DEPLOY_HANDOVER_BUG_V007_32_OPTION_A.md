# V007.32 — 选项 A 完整部署手册 (云控制台写 log_service.py)

> **作者**: dev-agent
> **日期**: 2026-07-07 16:25
> **状态**: 🚨 **P0 紧急** — yonaa 僵死, 协调智能体需要立即执行
> **用户选择**: 选项 A — 通过云控制台写文件

---

## 0. TL;DR

| 步骤 | 内容 | 时间 | 谁做 |
|------|------|------|------|
| 1 | 云控制台登录 yonaa (root) | 5 min | 协调智能体 |
| 2 | 写 log_service.py 到 /opt/app/deployments/ | 5 min | 协调智能体 |
| 3 | 启动 log_service (9101) | 1 min | 协调智能体 |
| 4 | 验证 9101 端口 | 1 min | 协调智能体 |
| 5 | 我读 server.log 精确定位根因 | 5 min | dev-agent (我) |
| 6 | 写 V007.33 根因报告 + 修复方案 | 30 min | dev-agent (我) |
| 7 | V007.29 P0 修复 (3h) | 3h | dev-agent (我) |
| 8 | 部署到 yonaa | 1.5h | 协调智能体 |
| 9 | 50 并发验证 | 0.5h | dev-agent (我) |
| **总计** | | **5-6h** | |

---

## 1. 完整步骤 (协调智能体)

### Step 1: 登录 yonaa 云控制台

**常用云控制台**:
- **阿里云**: https://ecs.console.aliyun.com → 实例 → 远程连接 → Workbench (root)
- **腾讯云**: https://console.cloud.tencent.com/cvm → 实例 → 登录 → 标准登录 (root)
- **AWS**: https://console.aws.amazon.com/ec2 → Instances → Connect → Session Manager
- **华为云**: https://console.huaweicloud.com/ecm → 远程登录 (root)
- **Azure**: https://portal.azure.com → Virtual Machines → Bastion

**或者物理 console**:
- IPMI / iLO / iDRAC
- 直接接键盘显示器

### Step 2: 写 log_service.py

#### 方法 1: 复制粘贴 (推荐)

1. **本地打开** [log_service.py](file:///D:/filework/integration-worktree/log_service.py) (我们刚 commit)
2. **复制整个文件内容** (约 200 行)
3. **云控制台终端执行**:
   ```bash
   cat > /opt/app/deployments/log_service.py << 'LOG_SERVICE_EOF'
   # 粘贴整个文件内容
   LOG_SERVICE_EOF
   ```

#### 方法 2: echo 一行一行

```bash
cd /opt/app/deployments
# 复制本地 log_service.py 到 yonaa (如果 user 机器能 scp 到 yonaa)
# 但 yonaa SSH 拒绝, 所以必须用 cat <<EOF
```

#### 方法 3: 用 base64 编码后粘贴

```bash
# 在本地 (Windows PowerShell)
[Convert]::ToBase64String([IO.File]::ReadAllBytes("D:\filework\integration-worktree\log_service.py"))
# 输出: aW1wb3J0IG9zCi...
```

```bash
# 在 yonaa 控制台
echo 'aW1wb3J0IG9zCi...' | base64 -d > /opt/app/deployments/log_service.py
chmod +x /opt/app/deployments/log_service.py
```

### Step 3: 启动 log_service

```bash
# 验证文件大小
ls -la /opt/app/deployments/log_service.py

# 启动
nohup python3 /opt/app/deployments/log_service.py > /tmp/log_service.log 2>&1 &
# 或 (如果没有 python3)
nohup python /opt/app/deployments/log_service.py > /tmp/log_service.log 2>&1 &

# 立即验证启动
sleep 2
cat /tmp/log_service.log
# 应该看到: [log_service] starting on 0.0.0.0:9101

# 检查进程
ps aux | grep log_service
# 应该看到 1 行 python log_service.py
```

### Step 4: 验证 9101 端口

```bash
# 防火墙 (如果需要)
sudo firewall-cmd --permanent --add-port=9101/tcp
sudo firewall-cmd --reload
# 或
sudo iptables -A INPUT -p tcp --dport 9101 -j ACCEPT
# 或
sudo ufw allow 9101/tcp

# 验证本地
curl http://localhost:9101/api/system
# 应该返回 JSON
```

### Step 5: 我读 log (dev-agent 做)

```bash
# 在协调智能体的本机 (Windows PowerShell)
# 我能立即调:
curl http://172.20.59.7:9101/api/system
curl http://172.20.59.7:9101/api/proc
curl http://172.20.59.7:9101/api/log?file=server.log&lines=200
curl http://172.20.59.7:9101/api/log?file=server.log&lines=500&grep=disk
curl http://172.20.59.7:9101/api/log?file=server.log&lines=500&grep=Operational
curl http://172.20.59.7:9101/api/db/health
curl http://172.20.59.7:9101/api/dmesg?lines=50&grep=OutOfMemory
```

### Step 6: 我精确定位根因 (dev-agent 做)

读 log 后, 我能:
- 找 30 min 前 disk I/O 错误具体在哪个 query
- 看 V007.16 mark_error / retry 实际触发
- 看 async_audit_writer 写 audit_logs 撞锁
- 看 WriteQueue backlog
- 看 db connection 死锁堆栈
- 看 server.py 启动时间 + 异常 trace

### Step 7: 我写 V007.33 根因报告 (dev-agent 做)

### Step 8: 协调智能体重启 server.py (如果我找到重启命令)

**v007.31 log_service 有 /api/restart endpoint**:
```bash
# 找 server.py 进程
curl http://172.20.59.7:9101/api/proc | python -c "import json,sys; d=json.load(sys.stdin); print('\n'.join([l for l in d['python_lines'] if 'server.py' in l]))"
```

**云控制台执行**:
```bash
# 看 server.py 进程
ps aux | grep -v grep | grep server.py

# 看 supervisord / systemd 配置
ls /etc/supervisor/conf.d/ 2>/dev/null
ls /etc/systemd/system/ 2>/dev/null | grep -i server
cat /etc/systemd/system/excel-backend.service 2>/dev/null

# 重启 (根据实际部署方式)
sudo systemctl restart excel-backend
# 或
sudo supervisorctl restart excel-backend
# 或 (手动)
pkill -TERM -f server.py
sleep 3
nohup python3 /opt/app/deployments/server.py > /opt/app/deployments/meta/server.log 2>&1 &
```

---

## 2. 完整 log_service.py (粘贴到云控制台)

[log_service.py](file:///D:/filework/integration-worktree/log_service.py) 已在本地仓库, **约 200 行**, 完整可运行。

**核心 6 个 endpoint**:

| Endpoint | 用途 |
|----------|------|
| `GET /api/system` | load / uptime / disk / memory / total fds |
| `GET /api/proc` | 所有 python/server.py 进程 |
| `GET /api/log?file=X&lines=N&grep=Y&before=Z` | 读 server.log (tail -N + grep) |
| `GET /api/db/health?db=path` | db 大小 / wal / shm / journal_mode / integrity / users / roles / audit_logs / recent disk errors |
| `GET /api/dmesg?lines=N&grep=Y` | kernel dmesg (查 OOM / segfault / panic) |
| `GET /api/restart?target=server.py&token=X` | SIGTERM server.py (token 验证) |

---

## 3. 协调智能体执行清单

### 立即 (Step 1-4, 12 min)

- [ ] 登录 yonaa 云控制台 (root)
- [ ] 复制本地 `D:\filework\integration-worktree\log_service.py` 全部内容
- [ ] 在 yonaa 控制台执行 `cat > /opt/app/deployments/log_service.py << 'EOF' ... EOF`
- [ ] 执行 `chmod +x /opt/app/deployments/log_service.py` (可选, Python 文件不需要)
- [ ] 执行 `nohup python3 /opt/app/deployments/log_service.py > /tmp/log_service.log 2>&1 &`
- [ ] 执行 `sleep 2 && cat /tmp/log_service.log`
- [ ] 执行 `curl http://localhost:9101/api/system` (验证)
- [ ] **告诉我**: 9101 端口验证结果

### 然后 (Step 5-6, 5 min)

- [ ] 我立即调 `curl http://172.20.59.7:9101/api/log?file=server.log&lines=500&grep=disk`
- [ ] 我立即调 `curl http://172.20.59.7:9101/api/db/health`
- [ ] 我立即调 `curl http://172.20.59.7:9101/api/dmesg?lines=100&grep=Out`
- [ ] 我分析 log, 找精确根因
- [ ] 我写 V007.33 报告 (5-10 min)

### 然后 (Step 7-9, 4h)

- [ ] 我实施 V007.29 P0 修复 (3h)
- [ ] 协调智能体重启 server.py (0.5h)
- [ ] 我跑 50 并发测试 (0.5h)

---

## 4. 关键问题

### 4.1 我无法直接帮你写文件到 yonaa

**我无法直接 SSH yonaa** (V007.30 已确认: SSH 拒绝)。
**我无法通过 HTTP 写文件** (unified_server 不支持)。
**我无法通过 yonaa Node Exporter 写文件** (只读 metrics)。

### 4.2 唯一可行: 协调智能体云控制台

**协调智能体必须有云控制台 root 权限**。

### 4.3 失败时的回退

如果协调智能体**没有云控制台**:
- **找云厂商 support** (阿里云/腾讯云/AWS support)
- **物理 console** (IPMI/iLO)
- **同事帮忙** (谁有 yonaa 物理/云访问权)

---

## 5. 我能立即在 log_service 上线后做的

| 步骤 | 动作 | 时间 |
|------|------|------|
| 1 | 读 server.log 最新 200 行 | 5 min |
| 2 | 读 db 健康状态 (integrity / journal_mode) | 1 min |
| 3 | 查 dmesg OOM | 1 min |
| 4 | 找 30 min 前 disk I/O 错误 | 5 min |
| 5 | 找 server.py 启动时间 + 异常 | 5 min |
| 6 | 找 audit_log 撞锁证据 | 5 min |
| 7 | 写 V007.33 精确根因报告 | 30 min |
| 8 | 实施 V007.29 P0 修复 (代码) | 3h |
| 9 | 部署 + 重启 + 验证 | 2h |

**总计 5h**。

---

## 6. 协调智能体 — 立即可做

**我需要协调智能体做的**:
1. 登录 yonaa 云控制台 (root)
2. 复制 [log_service.py](file:///D:/filework/integration-worktree/log_service.py) 全部内容
3. 在控制台粘贴 + 启动
4. 验证 9101 端口 OK
5. **告诉我 "log_service 已上线"**

**我立即**:
1. 读 server.log 精确定位根因
2. 写 V007.33 根因报告
3. 实施 V007.29 P0 修复

---

## 7. 风险评估

| 风险 | 缓解 |
|------|------|
| log_service 上线失败 | 我有详细启动命令 + 验证步骤 |
| 云控制台断网 | 重连 (云控制台通常很稳定) |
| 协调智能体无云控制台 | 找云厂商 support |
| 防火墙拦 9101 | 调 iptables / firewall-cmd / ufw |
| 复制粘贴出错 | 用 base64 编码 |
| log_service 自身僵死 | 独立进程, 跟 server.py 平行, 不影响诊断 |

---

## 8. Todo

| # | 任务 | 状态 |
|---|------|------|
| 1 | V007.21-V007.30 (8 个报告) | ✅ done |
| 2 | V007.31 (log_service 设计) | ✅ done |
| 3 | V007.32 (选项 A 完整手册) | ✅ done |
| 4 | **写 log_service.py 完整版** | ✅ done (200 行) |
| 5 | **协调智能体云控制台写 + 启动** | 🚧 **P0 紧急** |
| 6 | 我读 log + V007.33 根因报告 | 🚧 待 |
| 7 | V007.29 P0 修复 | 🚧 待 |
| 8 | 50 并发验证 | 🚧 待 |

---

## 9. 关键 — 协调智能体请立即回复

**协调智能体能登录 yonaa 云控制台吗?**

- **能**: 立即执行 Step 1-4 (12 min)
- **不能**: 找云厂商 support 或其他方式

**如果能, 立即**:
1. 复制 `D:\filework\integration-worktree\log_service.py` 全部内容
2. 在 yonaa 控制台粘贴执行
3. 启动 + 验证 9101
4. 告诉我"log_service 已上线"

**我会立即接管, 读 log + 找根因**。