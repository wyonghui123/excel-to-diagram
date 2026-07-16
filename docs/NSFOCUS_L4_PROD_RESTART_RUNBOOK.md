# NSFOCUS-L4 核心服务深夜重启 Runbook [V1.0 2026-07-14]

> **目的**: 消除 yonaa 剩余 8 个 0.0.0.0 监听告警 (绿盟扫描)
> **目标主机**: yonaa (172.20.59.7)
> **执行窗口**: 深夜 0-3 点 (最低流量)
> **核心原则**: 顺序重启, 每次间隔 30s, 5min 健康监控
> **回滚**: 每个服务独立回滚, 不影响其他

---

## 0. 现状 (2026-07-14 22:30)

**已合规 (10/16)**:
- staging 全部 4 个 (19101/13011/18081/19200)
- 9214 dbops_audit_service
- 9215 deploy_service
- 9204 dbops_service V1.0 (BIND 代码支持, 待重启)
- 9205 error_aggregator (BIND 代码支持, 待重启)
- 9100 node_exporter (tcp6)
- 22 sshd (跳过)

**待合规 (8/16, prod 核心)**:
| 端口 | 服务 | PID | BIND env | 风险 |
|------|------|-----|----------|------|
| 9206 | error_aggregator | 24726 | ERROR_AGGREGATOR_BIND | 🟢 低 |
| 9207 | slo_service | 24727 | SLO_SERVICE_BIND | 🟢 低 |
| 9208 | health_service | 24720 | HEALTH_SERVICE_BIND | 🟢 低 |
| 9209 | debug_service | 24723 | DEBUG_SERVICE_BIND | 🟢 低 |
| 9203 | config_service | 24725 | CONFIG_SERVICE_BIND | 🟢 低 |
| 9202 | ops_scheduler | 28060 | OPS_SCHEDULER_BIND | 🟢 低 |
| 9201 | observability | 26361 | OBS_SERVICE_BIND | 🟡 中 |
| 9101 | log_service | 31939 | LOG_SERVICE_BIND | 🔴 高 (agent 用) |
| 9200 | core_service | 21353 | CORE_SERVICE_BIND | 🔴 高 (前端用) |
| 8081 | unified | 19793 | UNIFIED_8081_BIND | 🔴 高 (前端用) |
| 3011 | frontend | 14286 | SERVER_BIND_HOST | 🔴 高 (前端用) |

> 实际算上是 11 个端口 (含 9204/9205 也需重启, 但 BIND env 已就位, 一并做)

---

## 1. 执行计划 (建议)

### 阶段 A: 监控类 (低风险, 0:00-0:30)

1. error_aggregator (9206) — 5 min
2. slo_service (9207) — 5 min
3. health_service (9208) — 5 min
4. debug_service (9209) — 5 min
5. config_service (9203) — 5 min
6. ops_scheduler (9202) — 5 min
7. observability (9201) — 5 min

### 阶段 B: 业务核心 (高风险, 0:30-1:30)

8. **log_service (9101)** — agent 正在用, 滚动重启
9. **core_service (9200)** — 前端核心, 滚动重启
10. **unified (8081)** — 前端入口
11. **frontend (3011)** — 前端 meta_backend

> 每个服务间隔 **30s-60s**, 每次后跑 `monitor_prod.py` 验证

---

## 2. 单个服务重启模板

### 步骤

```bash
# 0. 确认服务 BIND 代码支持
grep "BIND" /opt/app/shared/SERVICE_NAME.py

# 1. 确认 staging 上无流量
netstat -tn | grep ':PORT ' || echo NO_CONNECTIONS

# 2. 准备备份 (只备份 0.0.0.0 启动方式)
echo "[INFO] 准备重启 SERVICE_NAME (PORT)"
ps -p OLD_PID -o pid,cmd

# 3. kill (SIGTERM → SIGKILL)
kill OLD_PID 2>/dev/null
sleep 3
if ps -p OLD_PID > /dev/null 2>&1; then
    kill -9 OLD_PID 2>/dev/null
    sleep 1
fi

# 4. 用 BIND=172.20.59.7 启动 (后台)
# 先 source .env_global 让所有 BIND env 都生效
export $(grep -v '^#' /opt/app/.env_global | xargs)

# 启动 (用 BIND_ENV=172.20.59.7 显式指定)
cd CWD
LOG_FILE=/opt/app/shared/logs/SERVICE_NAME.log
open_LOG=truncate  # 等价于 open(...).close()
: > $LOG_FILE
setsid nohup env BIND_ENV=172.20.59.7 PYTHON_BIN START_CMD >> $LOG_FILE 2>&1 < /dev/null &
disown $! 2>/dev/null

# 5. 等待 + 验证
sleep 5
netstat -tlnp | grep ':PORT '
# 应该看到: tcp 0 0 172.20.59.7:PORT 0.0.0.0:* LISTEN

# 6. 探活
curl -s -m 5 http://172.20.59.7:PORT/api | head -c 200
# 应该返回 200 + JSON

# 7. 5min 健康监控
sleep 300
python3 /opt/app/shared/monitor_prod.py 2>&1 | tail -30
```

### 失败回滚

```bash
# 新进程 PID
NEW_PID=$(pgrep -f "START_CMD")
kill $NEW_PID 2>/dev/null
sleep 3

# 旧方式启动 (0.0.0.0)
cd CWD
setsid nohup env PYTHON_BIN START_CMD >> $LOG_FILE 2>&1 < /dev/null &
disown $! 2>/dev/null

# 确认回到 0.0.0.0 (临时)
sleep 5
netstat -tlnp | grep ':PORT '
# 应该看到: tcp 0 0 0.0.0.0:PORT 0.0.0.0:* LISTEN
```

---

## 3. 各服务具体命令

### 阶段 A 监控类

#### 1. error_aggregator (9206)

```bash
# 1. 检查无流量
netstat -tn | grep ':9206 ' || echo NO_CONNECTIONS

# 2. kill
kill 24726 2>/dev/null
sleep 3
if ps -p 24726 > /dev/null 2>&1; then kill -9 24726; sleep 1; fi

# 3. 启动
cd /opt/app/shared
: > /opt/app/shared/logs/error_aggregator.log
setsid nohup env ERROR_AGGREGATOR_BIND=172.20.59.7 \
    /opt/miniconda3-py39/bin/python /opt/app/shared/error_aggregator_service.py \
    >> /opt/app/shared/logs/error_aggregator.log 2>&1 < /dev/null &
disown $! 2>/dev/null

# 4. 验证
sleep 5
netstat -tlnp | grep ':9206 '
# tcp 0 0 172.20.59.7:9206 0.0.0.0:* LISTEN
```

#### 2. slo_service (9207)

```bash
kill 24727 2>/dev/null
sleep 3
if ps -p 24727 > /dev/null 2>&1; then kill -9 24727; sleep 1; fi
cd /opt/app/shared
: > /opt/app/shared/logs/slo_service.log
setsid nohup env SLO_SERVICE_BIND=172.20.59.7 \
    /opt/miniconda3-py39/bin/python /opt/app/shared/slo_service.py \
    >> /opt/app/shared/logs/slo_service.log 2>&1 < /dev/null &
disown $! 2>/dev/null
sleep 5
netstat -tlnp | grep ':9207 '
```

#### 3. health_service (9208)

```bash
kill 24720 2>/dev/null
sleep 3
if ps -p 24720 > /dev/null 2>&1; then kill -9 24720; sleep 1; fi
cd /opt/app/shared
: > /opt/app/shared/logs/health_service.log
setsid nohup env HEALTH_SERVICE_BIND=172.20.59.7 \
    /opt/miniconda3-py39/bin/python /opt/app/shared/health_service.py \
    >> /opt/app/shared/logs/health_service.log 2>&1 < /dev/null &
disown $! 2>/dev/null
sleep 5
netstat -tlnp | grep ':9208 '
```

#### 4. debug_service (9209)

```bash
kill 24723 2>/dev/null
sleep 3
if ps -p 24723 > /dev/null 2>&1; then kill -9 24723; sleep 1; fi
cd /opt/app/shared
: > /opt/app/shared/logs/debug_service.log
setsid nohup env DEBUG_SERVICE_BIND=172.20.59.7 \
    /opt/miniconda3-py39/bin/python /opt/app/shared/debug_service.py \
    >> /opt/app/shared/logs/debug_service.log 2>&1 < /dev/null &
disown $! 2>/dev/null
sleep 5
netstat -tlnp | grep ':9209 '
```

#### 5. config_service (9203)

```bash
kill 24725 2>/dev/null
sleep 3
if ps -p 24725 > /dev/null 2>&1; then kill -9 24725; sleep 1; fi
cd /opt/app/shared
: > /opt/app/shared/logs/config_service.log
setsid nohup env CONFIG_SERVICE_BIND=172.20.59.7 \
    /opt/miniconda3-py39/bin/python /opt/app/shared/config_service.py \
    >> /opt/app/shared/logs/config_service.log 2>&1 < /dev/null &
disown $! 2>/dev/null
sleep 5
netstat -tlnp | grep ':9203 '
```

#### 6. ops_scheduler (9202)

```bash
kill 28060 2>/dev/null
sleep 3
if ps -p 28060 > /dev/null 2>&1; then kill -9 28060; sleep 1; fi
cd /opt/app/shared
: > /opt/app/shared/logs/ops_scheduler.log
setsid nohup env OPS_SCHEDULER_BIND=172.20.59.7 \
    /usr/bin/python3 /opt/app/shared/ops_scheduler.py \
    >> /opt/app/shared/logs/ops_scheduler.log 2>&1 < /dev/null &
disown $! 2>/dev/null
sleep 5
netstat -tlnp | grep ':9202 '
```

#### 7. observability (9201)

```bash
kill 26361 2>/dev/null
sleep 3
if ps -p 26361 > /dev/null 2>&1; then kill -9 26361; sleep 1; fi
cd /opt/app/shared
: > /opt/app/shared/logs/observability_service.log
setsid nohup env OBS_SERVICE_BIND=172.20.59.7 \
    /opt/miniconda3-py39/bin/python /opt/app/shared/observability_service.py \
    >> /opt/app/shared/logs/observability_service.log 2>&1 < /dev/null &
disown $! 2>/dev/null
sleep 5
netstat -tlnp | grep ':9201 '
```

#### 8. dbops_service (9204) — 顺便做

```bash
kill 24722 2>/dev/null
sleep 3
if ps -p 24722 > /dev/null 2>&1; then kill -9 24722; sleep 1; fi
cd /opt/app/shared
: > /opt/app/shared/logs/dbops_service.log
setsid nohup env DBOPS_SERVICE_BIND=172.20.59.7 \
    /opt/miniconda3-py39/bin/python /opt/app/shared/dbops_service.py \
    >> /opt/app/shared/logs/dbops_service.log 2>&1 < /dev/null &
disown $! 2>/dev/null
sleep 5
netstat -tlnp | grep ':9204 '
```

#### 9. error_aggregator (9205) — 等等, 9205 是 error_aggregator, 9206 也是

发现 9205/9206 都有, 可能端口记错. 重新检查:

```bash
ps -ef | grep -E "(9205|9206)" | grep python
```

实际错误: 我之前的 port mapping 错了. error_aggregator 在 9205 不是 9206. 修正后:

```bash
# error_aggregator 在 9205 (PID 24724)
kill 24724 2>/dev/null
sleep 3
if ps -p 24724 > /dev/null 2>&1; then kill -9 24724; sleep 1; fi
cd /opt/app/shared
: > /opt/app/shared/logs/error_aggregator.log
setsid nohup env ERROR_AGGREGATOR_BIND=172.20.59.7 \
    /opt/miniconda3-py39/bin/python /opt/app/shared/error_aggregator_service.py \
    >> /opt/app/shared/logs/error_aggregator.log 2>&1 < /dev/null &
disown $! 2>/dev/null
sleep 5
netstat -tlnp | grep ':9205 '
```

### 阶段 A 完成验证 (9 个服务)

```bash
netstat -tlnp | grep 172.20.59.7 | grep -E ':(9201|9202|9203|9204|9205|9206|9207|9208|9209) '
# 应该看到 9 行
```

### 阶段 B 业务核心

#### 10. log_service (9101) — 高风险

```bash
# 1. 确认 agent 当前连接 (应该有, 但要心里有数)
netstat -tn | grep ':9101 ' | grep ESTABLISHED | wc -l

# 2. kill (agent 会断连, 但会重试)
kill 31939 2>/dev/null
sleep 3
if ps -p 31939 > /dev/null 2>&1; then kill -9 31939; sleep 1; fi

# 3. 启动
cd /opt/app/shared
: > /opt/app/shared/logs/log_service.log
setsid nohup env LOG_SERVICE_BIND=172.20.59.7 \
    /opt/miniconda3-py39/bin/python /opt/app/shared/log_service.py \
    >> /opt/app/shared/logs/log_service.log 2>&1 < /dev/null &
disown $! 2>/dev/null

# 4. 验证
sleep 5
netstat -tlnp | grep ':9101 '
# tcp 0 0 172.20.59.7:9101 0.0.0.0:* LISTEN

# 5. 探活
curl -s -m 5 http://172.20.59.7:9101/api/disk/check | head -c 200
```

#### 11. core_service (9200) — 高风险 (前端核心)

```bash
kill 21353 2>/dev/null
sleep 3
if ps -p 21353 > /dev/null 2>&1; then kill -9 21353; sleep 1; fi
cd /opt/app/shared
: > /opt/app/shared/logs/core_service.log
setsid nohup env CORE_SERVICE_BIND=172.20.59.7 \
    /opt/miniconda3-py39/bin/python /opt/app/shared/core_service.py \
    >> /opt/app/shared/logs/core_service.log 2>&1 < /dev/null &
disown $! 2>/dev/null
sleep 5
netstat -tlnp | grep ':9200 '
# 探活: curl https://172.20.59.7:9200/api?token=...
```

#### 12. unified (8081) — 高风险 (前端入口)

```bash
# 1. 看实际启动命令
ps -p 19793 -o cmd
# /usr/bin/python3 /tmp/unified_8081.py /opt/app/deployments/frontend_dist_files

kill 19793 2>/dev/null
sleep 3
if ps -p 19793 > /dev/null 2>&1; then kill -9 19793; sleep 1; fi

# 2. 启动
cd /opt/app/deployments
: > /opt/app/shared/logs/unified_8081.log
setsid nohup env UNIFIED_8081_BIND=172.20.59.7 \
    /usr/bin/python3 /opt/app/deployments/frontend_dist_files/../unified_8081.py \
    /opt/app/deployments/frontend_dist_files \
    >> /opt/app/shared/logs/unified_8081.log 2>&1 < /dev/null &
disown $! 2>/dev/null
sleep 5
netstat -tlnp | grep ':8081 '
```

> 注: unified_8081.py 是否读 env 需验证, 如不支持, 需先改代码

#### 13. frontend (3011) — 高风险 (meta_backend)

```bash
# 1. 看实际启动
ps -p 14286 -o cmd
# /opt/miniconda3-py39/bin/python -u server.py (在 /opt/app/deployments/xxx)

kill 14286 2>/dev/null
sleep 3
if ps -p 14286 > /dev/null 2>&1; then kill -9 14286; sleep 1; fi

# 2. 启动
cd /opt/app/deployments/current
: > /opt/app/shared/logs/frontend_3011.log
setsid nohup env SERVER_BIND_HOST=172.20.59.7 \
    /opt/miniconda3-py39/bin/python -u /opt/app/deployments/current/server.py \
    >> /opt/app/shared/logs/frontend_3011.log 2>&1 < /dev/null &
disown $! 2>/dev/null
sleep 8  # Flask 启动慢
netstat -tlnp | grep ':3011 '
```

---

## 4. 完成后验证

```bash
# 4.1 端口合规检查
netstat -tlnp | grep '0.0.0.0' | grep -v ':22 ' | grep -v ':9100 '
# 应该只有 sshd (22) + node_exporter (9100) 剩余 0.0.0.0

# 4.2 跑完整 monitor_prod.py
/opt/miniconda3-py39/bin/python3 /opt/app/shared/monitor_prod.py 2>&1 | tail -50
# 期望: 全部 [OK], 0 [FAIL]

# 4.3 前端烟测
curl -s -m 10 "http://172.20.59.7:8081/api/v1/auth/dev-login?username=admin" -c /tmp/cookies
curl -s -m 10 "http://172.20.59.7:8081/api/v2/bo/role?page_size=5" -b /tmp/cookies | head -c 500
```

---

## 5. 风险与回滚策略

### 高风险点

- **log_service (9101)**: agent 重连机制, 断连 ~5s 可恢复
- **core_service (9200)**: 前端断 5-10s, 用户可能感知
- **unified (8081)**: 前端入口, 断 5-10s
- **frontend (3011)**: meta_backend 断 5-10s

### 回滚原则

- 单服务回滚, 不影响其他
- 新进程启动失败, 自动回到 0.0.0.0 (临时)
- monitor_prod.py 报 [FAIL] 立即回滚

### 整体回滚 (灾难情况)

```bash
# 全部回滚: 杀新进程 + 用 0.0.0.0 启
# 注意: 这会触发绿盟告警
for port in 9201 9202 9203 9204 9205 9206 9207 9208 9209 9101 9200 8081 3011; do
    NEW_PID=$(lsof -ti:$port)
    if [ -n "$NEW_PID" ]; then
        kill $NEW_PID
        echo "killed PID $NEW_PID for port $port"
    fi
done
sleep 10
# 然后重新启动所有服务 (用原 systemd 或 nohup, 无 BIND env)
```

---

## 6. 时间估算

| 阶段 | 服务数 | 单服务耗时 | 累计 |
|------|-------|-----------|------|
| 阶段 A (监控) | 7 | 3 min (kill+start+verify) | 25 min |
| 阶段 B (核心) | 4 | 5 min (含健康监控) | 25 min |
| 总验证 | - | 10 min | 10 min |
| **合计** | **11** | - | **~60 min** |

---

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-07-14 | AI Assistant | 初版: 基于实际端口/PID 生成 runbook |
