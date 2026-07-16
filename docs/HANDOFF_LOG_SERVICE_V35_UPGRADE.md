# LOG_SERVICE v3.5 YONAA 升级交接 (部署智能体)

**接收方**: 部署智能体 (自己)
**任务**: yonaa log_service 从 v4 升级到 v3.5 (含 sqlite/load, iostat, proc/io 端点)
**触发**: dev-agent 修 V007.37 disk I/O error 需要 v3.5 端点做根因排查
**时间**: 2026-07-08

---

## 1. 现状 (已远程确认 07:55)

| 端点 | 状态 | 版本 |
|------|------|------|
| /api/metrics | ✅ Prometheus 格式 | **v4** |
| /api/dmesg, /api/db/health, /api/log, /api/proc | ✅ | **v4** |
| /api/sqlite | ❌ | 缺 |
| /api/sqlite/load | ❌ | 缺 |
| /api/iostat | ❌ | 缺 |
| /api/proc/io | ❌ | 缺 |
| /api/config | ❌ | 缺 (v4 才有, 但 yonaa 没有说明是 v3?) |

**结论**: yonaa 跑 v4 (我之前部署的), **不是 dev-agent v3.5**。

## 2. 目标

把 yonaa log_service 升级到 v3.5 (含 4 个新端点), **不破坏** v4 已有的 18 端点。

## 3. 升级方案

### 3.1 选项对比

| 方案 | 优点 | 缺点 |
|------|------|------|
| A. 用 dev-agent v3.5 覆盖 v4 | 包含 4 个新端点 | 失去 v4 的 18 个端点 (回退) |
| B. 把 v3.5 的 4 个端点合并到 v4 | 保留 v4 所有 + 加 v3.5 | 需手动 merge 代码 |
| C. 用 dev-agent 的 v3.5 但保留 v4 文件读端点 | 折中 | 工作量中等 |

**选 B** (合并方案)。理由：
- v4 是我之前部署验证过的，18 端点全工作
- v3.5 是 dev-agent 的，4 个新端点是排查 disk I/O 必需
- 合并 = 22 端点 (18+4)，覆盖 dev-agent 全部能力

### 3.2 合并步骤

**Step 1**: 本地 dev-agent v3.5 源文件 → 合并到 release-prep-worktree/tools/log_service.py

**Step 2**: 解决 Python 3.9 兼容 (datetime | None 已修, 其他 type hint 检查)

**Step 3**: 测试 22 端点本地全工作

**Step 4**: rebuild_zip 打包 + verify_bundle PASS

**Step 5**: SFTP 上传到 yonaa + 重启 log_service

**Step 6**: 远程验证 22 端点 + 监控业务 disk I/O 计数变化

## 4. dev-agent v3.5 源文件

**Windows 本地路径**: `D:\filework\integration-worktree\log_service.py`
**大小**: 15238 字节 (328 行)
**远端目标**: `/opt/app/deployments/log_service.py`

## 5. yonaa 重启命令 (SSH)

```bash
# 1. 强杀
pkill -9 -f "log_service" 2>/dev/null
sleep 2

# 2. 验证端口释放
ss -tlnp | grep ":9101" && echo "[WARN] still listening" || echo "[OK] free"

# 3. 启动 v3.5 (合并版, 含 v4 端点 + v3.5 新端点)
nohup python3 /opt/app/deployments/log_service.py > /tmp/log_service_v35_merged.log 2>&1 &
NEW_PID=$!
echo "started PID=$NEW_PID"

# 4. 等启动
sleep 2

# 5. 验证 (所有 22 端点)
if kill -0 $NEW_PID 2>/dev/null; then
  echo "[OK] log_service v3.5-merged PID=$NEW_PID"
  curl -s http://127.0.0.1:9101/api/system | head -c 500
  echo ""
else
  echo "[FAIL] startup failed:"
  cat /tmp/log_service_v35_merged.log
fi
```

## 6. 验证清单 (部署后)

### 6.1 v4 端点 (18 个, 全部已工作)

```
GET /api/system
GET /api/dmesg
GET /api/db/health
GET /api/db/tables
GET /api/db/query
GET /api/log
GET /api/log/stream
GET /api/log/range
GET /api/proc
GET /api/find
GET /api/fd
GET /api/env
GET /api/exec
GET /api/metrics
+ 其他 v4 端点
```

### 6.2 v3.5 新端点 (4 个)

```
GET /api/sqlite?sql=SELECT count(*) FROM users
GET /api/sqlite/load?count=200&table=users
GET /api/iostat?count=3
GET /api/proc/io?pid=<pid>
```

### 6.3 安全白名单

```
GET /api/sqlite?sql=DROP TABLE users   → 必须 403
GET /api/iostat?count=999              → 必须限制 ≤10
GET /api/proc/io?pid=abc               → 必须拒绝非数字
```

## 7. invariant V8e (防 log_service 版本退化)

在 `tools/verify_bundle.py` 加：

```python
def check_v8e_zip_log_service_v35_endpoints() -> tuple:
    """V8e. log_service 必须含 v3.5 新端点: sqlite, sqlite/load, iostat, proc/io"""
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            ls = zf.read("tools/log_service.py").decode("utf-8", errors="ignore")
        needed = ["/api/sqlite", "/api/sqlite/load", "/api/iostat", "/api/proc/io"]
        missing = [n for n in needed if n not in ls]
        if missing:
            return (False, f"log_service.py 缺 v3.5 端点: {missing}")
        return (True, f"log_service.py 含 {len(needed)} 个 v3.5 端点")
    except Exception as e:
        return (False, f"读 log_service.py 失败: {e}")
```

## 8. dev-agent V3.5 升级失败原因分析 (历史)

之前 (23:30) 我以为 v3.5 已部署，实际是 **v4 覆盖**了 v3.5：

1. dev-agent 给了我 v3.5 → 我手动 SSH 启动 → 短期 OK
2. 之后 `deploy.sh --version v20260725_002` 触发 PHASE 8 → 自动启动 **v4** 覆盖
3. v3.5 被 **v4 替换**

**教训**: deploy.sh PHASE 8 启动的是 **bundle 内 log_service.py**，不是 dev-agent 的 v3.5。**必须在 deploy_bundle/tools/log_service.py 内含 v3.5 端点，才能在 PHASE 8 启动时合并部署**。

## 9. 工作清单

- [ ] Step 1: 把 dev-agent v3.5 的 4 个新端点合并到 release-prep-worktree/tools/log_service.py
- [ ] Step 2: Python 3.9 兼容 (datetime | None 用 from __future__ import annotations)
- [ ] Step 3: 本地测试 22 端点
- [ ] Step 4: rebuild_zip + verify_bundle 9+1=V8e PASS
- [ ] Step 5: SFTP 上传 deploy_bundle 到 yonaa
- [ ] Step 6: SSH 重启 log_service
- [ ] Step 7: 远程验证 22 端点
- [ ] Step 8: 监控 disk I/O error 计数变化 (配合 dev-agent V007.37 代码 fix)

---

**yonaa 服务清单** (截至 07:55):
- 5001 backend (V007.36, PID 20187, 47 fds)
- 8081 unified (PID 20212, 4 fds)
- 9101 log_service v4 (PID 20364, 6 fds) ← **升级目标**
- 9100 node_exporter (PID 578)

---

**状态**: 等待 dev-agent 完成 V007.37 fix (PRAGMA 幂等化 + export retry)，同时我做 log_service v3.5 合并升级