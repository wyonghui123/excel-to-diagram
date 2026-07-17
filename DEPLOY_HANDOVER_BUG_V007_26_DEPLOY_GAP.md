# V007.26 紧急 — Production disk I/O error 又发生 (部署断层)

> **作者**: dev-agent
> **日期**: 2026-07-07 14:30
> **状态**: 🚨 **P0 紧急** - V007.24 修复从未部署到生产
> **关联**: 
> - [DEPLOY_HANDOVER_BUG_V007_21_PROD.md](./DEPLOY_HANDOVER_BUG_V007_21_PROD.md) (原 7/7 8:21 IO error)
> - [DEPLOY_HANDOVER_BUG_V007_25_FINAL.md](./DEPLOY_HANDOVER_BUG_V007_25_FINAL.md) (V007.25 P0 已修)
> - [SPEC_V007_24_DETAILED.md](./SPEC_V007_24_DETAILED.md) (V007.24 spec)

---

## 0. TL;DR

| 字段 | 值 |
|------|-----|
| BUG-ID | **V007.26 production disk I/O error (再次发生)** |
| 严重度 | **P0-Critical** (生产环境故障) |
| 真因 | **V007.24 Phase 1 修复** `93b6381` **从未部署到生产 yonaa** |
| 修复时间 | **2-4h** (紧急 cherry-pick + 部署) |

---

## 1. 紧急现象 (刚刚发生)

### 1.1 yonaa 当前 API 状态

| Endpoint | yonaa 现状 | 期望 |
|----------|-----------|------|
| `POST /api/v2/action/user.authenticate` | **`{"data":null,"message":"disk I/O error","success":false}`** ❌ | 200 ✅ |
| `GET /api/v1/users/me` | **500 内部错误** ❌ | 401 UNAUTHORIZED ✅ |
| `GET /api/v2/meta/health` | **500** ❌ | 200 with health JSON ✅ |
| `GET /api/v1/management-dimensions` | **410 Gone (无 redirect info)** ❌ | 410 API Moved + redirect ✅ |

### 1.2 yonaa 端点路径对比 (跟 3006/3007)

| Endpoint | yonaa | 3006/3007 |
|----------|-------|-----------|
| `/api/v2/bo/user/me` | **404 NOT FOUND** ❌ | 401 UNAUTHORIZED ✅ |
| `/api/v1/db/status` | **410 Gone (裸)** ❌ | 410 API Moved ✅ |

**yonaa 部署的 server.py 是比 3006/3007 更老的版本**!

---

## 2. 完整根因 — V007.24 部署断层

### 2.1 worktrees/release-prep 主分支状态

```
release/pre-2026-06-29:
  630df25 fix(infra): V007.25 完整部署保障 (14:44 修复 + 6 层防护)  ← 最新
  82f7845 fix(v007.16): repair disk I/O error - is_valid + reader cache root cause
  39c2156 fix(v007.20): annotation import 1w+ skip_audit + WriteQueue retry + busy_timeout 30s
  ...
```

**`git merge-base --is-ancestor 93b6381 release/pre-2026-06-29`** → **False**!

**V007.24 Phase 1 commit `93b6381` 不在 release/pre-2026-06-29 主分支上!**

### 2.2 datasource.py 状态对比 (部署真相)

| 位置 | 是否有 _data_source_cache |
|------|--------------------------|
| `release/pre-2026-06-29:meta/core/datasource.py` | ❌ **没有** (依然 V007.16 老版) |
| `worktrees/integration:meta/core/datasource.py` | ✅ 有 (V007.24 Phase 1) |

**yonaa 部署的 `datasource.py` 跟 worktrees/release-prep 一样, 都没有 V007.24 cache**!

### 2.3 部署断层时间线

```
2026-07-07 06:00  V007.16 部署 (修 disk I/O)
2026-07-07 08:21  V007.21 8:20 IO error (V007.16 已修)
2026-07-07 09:25  V007.22 重新启动 server.py
2026-07-07 14:25  V007.24 Phase 1 commit (in worktrees/integration)
2026-07-07 14:30  V007.25 P0 (admin dim scope) 修复 yonaa db
2026-07-07 14:30  ❌ V007.24 未 cherry-pick 到 release/pre-2026-06-29
2026-07-07 14:30  ❌ V007.24 未部署到 yonaa
2026-07-07 14:35  ❌ V007.26 production disk I/O error 又发生
```

### 2.4 真正的根因 (3 层)

| Layer | 真因 | 证据 |
|-------|------|------|
| **A** | V007.24 Phase 1 `93b6381` 在 worktrees/integration, **未 cherry-pick** 到 release/pre-2026-06-29 | `git merge-base --is-ancestor` 返回 False |
| **B** | 即使 commit 存在, **打包 zip 时被漏掉**, 因为 release/pre-2026-06-29 没有这个 commit | `rebuild_zip.py` 只打包所在分支的 HEAD |
| **C** | yonaa 端仍然跑老的 lazy init 模式 (30+ 文件 `_data_source = None`), 每次 v2 BOAction 创建新 pool | 自 V007.21 以来这个 lazy init 模式没修过 |

**3 层叠加, 导致即使重启 yonaa 也会立即再次 IO error**!

---

## 3. 完整的"灾难"事件链

```
用户 admin 在前端登录
     ↓
POST /api/v2/action/user.authenticate
     ↓
meta.api.bo_action_api 路由到 BOActionRegistry
     ↓
user_authenticate handler 调 _get_auth_provider()
     ↓
[LAYER C - 老代码] user_authenticate.py:31 _data_source = None (lazy init)
     ↓
[LAYER C] _data_source.is None → 创建新 DataSource
     ↓
[LAYER C] get_data_source() 没缓存 (老代码) → 每次 new SQLiteConnectionPool
     ↓
[LAYER C] 新 pool 持有新 wal fd
     ↓
[LAYER A] yonaa 没 V007.24 cache, 重复触发 old fd leak (Layer 3 in V007.24 spec)
     ↓
新 connection 第一个 query (SELECT FROM users WHERE username='admin')
     ↓
sqlite3.OperationalError: disk I/O error
     ↓
返回 error 给前端
```

**这跟 V007.21 是同一个根因**, 只是 V007.24 修复**从未部署到生产**。

---

## 4. 紧急修复 (5 步)

### Step 1: 立即 — 紧急重启 yonaa server.py (临时缓解)

**操作**:
```bash
ssh user@172.20.59.7
# 重启 server.py (PID 替换)
sudo kill -HUP $(pgrep -f "server.py")
# 或
sudo systemctl restart excel-backend
```

**效果**: 清掉当前 stale fd 持有者, 但**只能缓解, 根因还在**。

### Step 2: 1-2h — Cherry-pick V007.24 Phase 1 到 worktrees/release-prep

**在 worktrees/integration cherry-pick 到 worktrees/release-prep**:

```bash
cd d:/filework/worktrees/release-prep

# 1. 切换到 release/pre-2026-06-29
git checkout release/pre-2026-06-29

# 2. Cherry-pick V007.24 Phase 1
git cherry-pick 93b6381
# 处理任何冲突 (datasource.py 之前在 release 分支可能也有过改动)

# 3. Cherry-pick V007.24 handover docs (78d2636)
git cherry-pick 78d2636

# 4. 跑 unit test
python -m pytest meta/tests/test_datasource_cache.py -v
```

**预期**: 4 个 unit test 通过。

### Step 3: 0.5h — 重新打包 deploy_bundle

```bash
cd d:/filework/worktrees/release-prep/tools
python rebuild_zip.py
# 自动 dry-run (强制, V007.25 修复过)
```

**预期**: zip 包含 V007.24 修复的 `datasource.py` + observability + metric。

### Step 4: 1-2h — 重新部署到 yonaa

```bash
# 1. 上传 zip 到 yonaa
scp deploy-v*.zip user@172.20.59.7:/tmp/

# 2. SSH yonaa 跑部署
ssh user@172.20.59.7
cd /opt/app/deployments
bash deploy.sh

# 3. 验证 V007.24 生效
curl http://172.20.59.7:8081/_metrics | grep v007_24_pool_init_count
# 期望: 1-2 (server.py main + AsyncAuditWriter)
```

### Step 5: 0.5h — 加部署 invariant 防止再发生

**修改 `tools/verify_bundle.py` 加 invariant V14**:
```python
# V14: 检查 datasource.py 必须有 _data_source_cache
def verify_v14_datasource_cache():
    zip_datasource = unzip_and_read('meta/core/datasource.py')
    if '_data_source_cache' not in zip_datasource:
        return False, 'zip datasource.py missing _data_source_cache (V007.24 not deployed)'
    return True, 'OK'
```

---

## 5. 跟 V007.21 / V007.24 的关系

| Bug | 真因 | 修复 | 部署状态 |
|-----|------|------|---------|
| **V007.21** | server.py 启动 TRUNCATE + 多 reader fd deleted | V007.16 (is_valid + reader cache) | ✅ 已部署 |
| **V007.22** | 同上, 进程未重启 | (无修复, 临时) | — |
| **V007.23** | 3 个 user_authenticate 独立 pool | V007.24 Phase 1 (DataSource cache) | ❌ **未部署!** |
| **V007.24 Phase 1** | 30+ 文件 lazy init + get_data_source 无缓存 | commit `93b6381` | ❌ **未部署!** |
| **V007.25** | admin db 缺 dim scope + 部署 redirect | P0 (db INSERT) 已部署 | ✅ P0 已修, P1/P2 待 |
| **V007.26** (现在) | V007.24 未部署导致 lazy init 复发 | cherry-pick `93b6381` | 🚨 **紧急处理中** |

**V007.26 = V007.24 部署断层**!

---

## 6. 协调智能体紧急决策项

### 6.1 立即 (30 min) — 不要等修复

1. **SSH yonaa 重启 server.py** — 临时缓解当前的 IO error
2. **通知用户 yonaa 暂时不可用** — 服务降级

### 6.2 紧急修复 (2-4h)

1. **cherry-pick `93b6381` 到 worktrees/release-prep** — Step 2
2. **重新打包 deploy_bundle** — Step 3
3. **部署到 yonaa** — Step 4
4. **验证 V007.24 生效** — Step 4 末

### 6.3 长期防御 (1 day)

1. **加 verify_bundle.py V14 invariant** — Step 5
2. **加 e2e 测试** — 验证 V007.24 cache 在生产生效
3. **加 observability 告警** — pool_init_count > 10 报警

### 6.4 不要做

- ❌ 不要回滚 V007.25 P0 (admin dim scope 修复是对的)
- ❌ 不要重新部署 V007.16 (老版本, 已修过)
- ❌ 不要改 worktrees/release-prep 的 deploy.sh (V007.25 已经加固过了)

---

## 7. 文件改动清单

| 文件 | 改动 | 时间 |
|------|------|------|
| `release/pre-2026-06-29:meta/core/datasource.py` | cherry-pick V007.24 Phase 1 | 1-2h |
| `release/pre-2026-06-29:meta/core/observability.py` | 加 v007_24_pool_init_count | 1-2h |
| `worktrees/release-prep/tools/verify_bundle.py` | 加 V14 invariant | 0.5h |
| `worktrees/release-prep/deploy-v*.zip` | 重新打包 | 0.5h |
| yonaa `/opt/app/deployments/meta/` | 重新部署 | 1-2h |

**总计**: 4-6h (半天)

---

## 8. 这次诊断的教训 (重要!)

### 8.1 我之前的 V007.24 报告 (commit `93b6381`)

我之前 commit `93b6381` 写了:
> "建议部署 (4h 修核心, 立即减少 38 → 1 init)"
> "可立即部署"
> "建议: 先在 yonaa 部署 V007.21, 观察效果。如果 init 数 ≤ 3, 不需要 Phase 2-4"

但我**没强调**: **V007.24 必须 cherry-pick 到 worktrees/release-prep 然后才能部署到 yonaa**!

这是我的失职。我之前以为 yonaa 会自动 cherry-pick, 实际上 yonaa 是从 `worktrees/release-prep` 部署, 而 V007.24 commit `93b6381` 只在 `worktrees/integration` 主分支上!

### 8.2 给协调智能体的建议

1. **永远确认 commit 在 worktrees/release-prep 主分支上** 才能部署
2. **永远 verify zip 内的代码 md5 跟 HEAD 一致** 才能部署
3. **永远 SSH yonaa 验证修复生效** (不能相信本机)

### 8.3 给未来 dev-agent 的建议

1. **永远跟踪 worktrees/release-prep 主分支历史**, 不只是 worktrees/integration
2. **永远先 cherry-pick 再打包再部署**, 而不是先 commit 再部署

---

## 9. 完整 git 历史状态

### 9.1 worktrees/release-prep (主分支 release/pre-2026-06-29) ❌

```
630df25 fix(infra): V007.25 完整部署保障 (14:44 修复 + 6 层防护)  ← HEAD
82f7845 fix(v007.16): repair disk I/O error
39c2156 fix(v007.20): annotation import
...
# 没有 V007.24 commit
```

### 9.2 worktrees/integration ✅

```
93b6381 fix(v007.24-phase1): DataSource 缓存 + metric 上报 ← V007.24 在这里
ab8da53 docs(spec): V007.24 DETAILED
6c4e16e docs(handover): V007.25 角色管理维度 - 终极真相
ba08f31 docs(handover): V007.25 角色管理维度为空 - 第 3 次真因
78d2636 docs(handover): V007.24 根因
48d8692 docs(handover): 角色详情管理维度为空 - 第 3 次根因分析
0bd3720 docs(handover): V007.23 根因
9a7928a docs(handover): V007.21 production event
```

**V007.24 在 worktrees/integration, 不在 worktrees/release-prep**!

---

## 10. 立即建议 (按紧急度)

### 优先级 P0 (紧急 - 30 min):
- SSH yonaa 重启 server.py, 临时缓解当前 IO error

### 优先级 P1 (1-2h):
- cherry-pick V007.24 `93b6381` + `78d2636` 到 worktrees/release-prep

### 优先级 P2 (0.5h):
- 重新打包 deploy_bundle (rebuild_zip.py)

### 优先级 P3 (1-2h):
- 部署到 yonaa + 验证

### 优先级 P4 (0.5h):
- 加 verify_bundle.py V14 invariant (防再发生)

**总时间**: 4-5h

---

## 11. 完整文件清单

### 11.1 需要 cherry-pick 到 worktrees/release-prep

| commit | 内容 |
|--------|------|
| `93b6381` | fix(v007.24-phase1): DataSource 缓存 + metric 上报 |
| `78d2636` | docs(handover): V007.24 根因与 V007.21 因果关系分析 |

### 11.2 可能冲突 (datasource.py)

release/pre-2026-06-29 上的 `datasource.py` (V007.16 后期):
- L112 "其他参数" (跟 3006 一样)
- 不含 `_data_source_cache`

worktrees/integration 上的 `datasource.py` (V007.24 Phase 1):
- L112 "其他参数" (跟 3006 一样)
- 含 `_data_source_cache` (新增)

**冲突可能在 L110-L160 (get_data_source 函数)**:
- 老版: 直接调用 `DataSourceFactory.create(dst, **kwargs)`
- 新版: 加 `_data_source_cache` + 单例缓存

**修复方式**: 用新版覆盖老版 (新版的语义是 superset)。

---

## 12. 协调智能体 — 请立即决议

**问题**: yonaa 当前 disk I/O error, admin 看不到登录, 大量用户受影响。

**选项**:
- **A. 立即 SSH 重启 server.py (30 min 缓解)** — 但 1-2h 后可能再 IO error
- **B. A + 同时 cherry-pick V007.24 (4-5h 完整修复)**
- **C. 直接完整 cherry-pick + 重新打包 + 部署 (4-5h, 不重启临时缓解)**

**我推荐 B** — 立即缓解 + 完整修复, 总时间 4-5h, 但用户在前 30 min 就能重新登录 (临时重启后)。