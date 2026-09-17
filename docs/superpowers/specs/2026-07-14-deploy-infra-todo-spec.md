# SPEC: 打包部署基础设施迭代 TODO (基于 2026-07-14 最新状态)

> **日期**: 2026-07-14
> **状态**: Draft
> **来源**: TODO_LONGTERM.md L8-L17 + NSFOCUS 绿盟合规修复 + delta 部署实测
> **目标**: 明确每项 TODO 的**实际完成度**、**剩余工作**、**与 NSFOCUS 合规的关联**，形成可执行 spec

---

## 0. TL;DR — 实际完成度总览

| # | TODO | 代码已写 | 单元测试 | 部署到 yonaa | NSFOCUS 关联 | 总体状态 |
|---|------|---------|---------|-------------|-------------|---------|
| **L8.6** | unzip_safe.py | ✅ 已写 | ✅ test_unzip_safe.py | ❌ 未部署 | 低 | 🟡 代码就绪 |
| **L8.8** | /api/isolation_check | ✅ 已写入 core_service | ⚠️ 无独立测试 | ❌ 未部署 | 低 | 🟡 代码就绪 |
| **L12** | /api/exec/session | ✅ 已写入 core_service | ⚠️ 无独立测试 | ❌ 未部署 | 低 | 🟡 代码就绪 |
| **L13.3** | dbops_service.py (9204) | ✅ 已写 | ⚠️ 跳过 | ❌ 未部署 (9204 被 error_aggregator 占用) | 低 | 🔴 **端口冲突** |
| **L13.4** | audit_coverage_check.py | ✅ 已写 | ✅ test_audit_coverage.py | ❌ 未部署 | 低 | 🟡 代码就绪 |
| **L14** | deploy_service.py (9205) | ✅ 已写 (模拟版) | ⚠️ test 跳过 | ❌ 未部署 (9205 被 error_aggregator 占用) | 低 | 🔴 **未接入 deploy.sh** |
| **L15** | monitor_prod.py 演进 | ❌ 未更新 | N/A | 部分在 yonaa (V007.67) | 中 | 🟡 **半完成** |
| **L17** | 智能 delta 部署 | ✅ 全部代码就绪 | ✅ test_delta_manifest.py | ✅ 3 个工具已部署到 /opt/app/shared/ | 低 | 🟢 **代码完成，集成待做** |
| **NSFOCUS-L4** | BIND=172.20.59.7 | ✅ .env_global 已部署 | N/A | ⚠️ 服务未重启 | **高** | 🔴 **核心待办** |
| **NSFOCUS-L7.f** | SSH 禁密码 | N/A | N/A | ❌ 未改 | 中 | 🟡 待确认 key |

---

## 1. L8.6 unzip_safe.py — magic number 检测 + multipart 剥离

### 1.1 当前状态

- ✅ `tools/unzip_safe.py` 代码完成 (detect_magic / auto_strip_multipart / check_file / CLI)
- ✅ `tools/tests/test_unzip_safe.py` 单元测试完成
- ❌ **未集成到 deploy.sh PHASE 0.5**
- ❌ **未部署到 yonaa /opt/app/shared/**

### 1.2 剩余工作

| Step | 内容 | 工作量 | 优先级 |
|------|------|--------|--------|
| 1.2.1 | 在 `deploy_bundle/deploy.sh` PHASE 0.5 smart_extract 后加 unzip_safe 调用 | 0.1d | P1 |
| 1.2.2 | 上传 `unzip_safe.py` 到 yonaa `/opt/app/shared/` | 0.05d | P1 |
| 1.2.3 | 在 yonaa 跑 `python3 /opt/app/shared/unzip_safe.py /opt/app/shared --recursive` 验证 | 0.05d | P1 |

### 1.3 deploy.sh 集成代码

在 `deploy.sh` smart_extract 完成后 (约 L200) 加:

```bash
# [L8.6] 检测文件 magic number 污染
if [ -x "$SHARED_DIR/unzip_safe.py" ]; then
    python3 "$SHARED_DIR/unzip_safe.py" "$DEPLOYMENTS_DIR" --recursive --check 2>&1
    if [ $? -ne 0 ]; then
        warn "发现污染文件, 请检查 magic number"
        # 不 abort, 仅警告 (deploy 可继续, 但需人工确认)
    fi
fi
```

### 1.4 验收标准

- [ ] deploy.sh PHASE 0.5 集成 unzip_safe --check
- [ ] yonaa /opt/app/shared/unzip_safe.py 可执行
- [ ] yonaa 上 `python3 unzip_safe.py /opt/app/shared --recursive` 0 polluted

---

## 2. L8.8 /api/isolation_check — PrivateTmp 隔离检测

### 2.1 当前状态

- ✅ 已写入 `tools/core_service.py` L334+ (`_isolation_check` 方法)
- ✅ 路由已注册 L222
- ✅ core_service 已支持 BIND 环境变量 (L39: `BIND = os.environ.get("CORE_SERVICE_BIND", "0.0.0.0")`)
- ❌ **未部署到 yonaa** (yonaa 上的 core_service 还是旧版)
- ❌ 无独立单元测试

### 2.2 剩余工作

| Step | 内容 | 工作量 | 优先级 |
|------|------|--------|--------|
| 2.2.1 | 上传新版 core_service.py 到 yonaa | 与 NSFOCUS-L4 绑定 | P1 |
| 2.2.2 | 重启 core_service (读 BIND=172.20.59.7) | 与 NSFOCUS-L4 绑定 | P1 |
| 2.2.3 | 验证 /api/isolation_check 返回 200 | 0.05d | P1 |

### 2.3 与 NSFOCUS-L4 的关系

**L8.8 和 NSFOCUS-L4 必须一起做**:
- 新版 core_service.py 已有 BIND 支持
- 部署新版 + 重启 = 同时解决 L4(0.0.0.0→172.20.59.7) 和 L8.8(isolation_check)
- **风险**: 重启会断前端 5-10s，需深夜执行

### 2.4 验收标准

- [ ] yonaa 上 core_service 重启后 BIND=172.20.59.7 (netstat 验证)
- [ ] GET /api/isolation_check 返回 200 + JSON
- [ ] monitor_prod.py 集成 isolation_check section

---

## 3. L12 /api/exec/session — Shell 会话保持

### 3.1 当前状态

- ✅ 已写入 `tools/core_service.py` L413+ (`_exec_session_create` / `_run` / `_state` / `_destroy`)
- ✅ 路由已注册 L224-226
- ✅ SESSIONS 全局状态 L45-48
- ✅ TTL 1h + max 50 session
- ❌ **未部署到 yonaa** (同 L8.8，绑定 core_service 更新)
- ❌ 无独立单元测试
- ❌ `remote_helper.py` 未适配 session 模式

### 3.2 剩余工作

| Step | 内容 | 工作量 | 优先级 |
|------|------|--------|--------|
| 3.2.1 | core_service 部署 (同 L8.8) | 已绑定 | P1 |
| 3.2.2 | `remote_helper.py` 加 session 模式 | 0.5d | P2 |
| 3.2.3 | 端到端测试 (create → cd → pwd → destroy) | 0.2d | P1 |

### 3.3 remote_helper.py 适配

当前 `remote_helper.py` 每次调用 `/api/exec` 都是独立命令。加 session 模式:

```python
class RemoteSession:
    """L12 exec/session 客户端封装"""
    def __init__(self, host, port=9200, secret=""):
        self.host = host
        self.port = port
        self.sid = None

    def __enter__(self):
        self.sid = self._create_session()
        return self

    def __exit__(self, *args):
        self._destroy_session()

    def run(self, cmd: str, timeout: int = 30) -> dict:
        """在 session 中执行命令 (保持 cwd/env)"""
        ...

    def cd(self, path: str):
        self.run(f"cd {path}")
```

### 3.4 验收标准

- [ ] POST /api/exec/session 返回 session_id
- [ ] 连续 cd + pwd 返回正确路径
- [ ] TTL 过期自动清理
- [ ] remote_helper.py 支持 RemoteSession

---

## 4. L13.3 dbops_service.py (9204) — audit_recovery HTTP API

### 4.1 当前状态

- ✅ `tools/dbops_service.py` 代码完成 (find/preview/restore 3 端点)
- ✅ L11.3 二次确认 (confirm=yes-i-know)
- ✅ 延迟导入 audit_recovery (ImportError 时降级)
- ✅ `tools/dbops_service.service` systemd unit 文件
- ❌ **端口冲突**: yonaa 9204 已被 V007.62 error_aggregator 占用
- ❌ **未部署到 yonaa**
- ❌ audit_recovery.py 未上传到 yonaa /opt/app/shared/

### 4.2 端口冲突问题

V007.66 部署事故 (2026-07-14): yonaa 上 9204 已被 error_aggregator 占用。

**选项**:
- **A**: 使用 9214 端口 (新分配) — 推荐，避免冲突
- **B**: 停掉 error_aggregator，释放 9204 — 需确认是否有依赖

### 4.3 剩余工作

| Step | 内容 | 工作量 | 优先级 |
|------|------|--------|--------|
| 4.3.1 | 确认端口 (9214 或 9204) | 需用户确认 | P0 |
| 4.3.2 | 上传 audit_recovery.py 到 /opt/app/shared/ | 0.05d | P0 |
| 4.3.3 | 上传 dbops_service.py + systemd unit | 0.05d | P0 |
| 4.3.4 | 启动 + 端到端测试 | 0.2d | P0 |

### 4.4 验收标准

- [ ] dbops_service 监听 9214 (或 9204)
- [ ] GET /api 返回服务信息
- [ ] GET /api/audit/recover/find 返回可恢复实体
- [ ] dry_run=false 需要 confirm=yes-i-know
- [ ] systemd unit enable + 启动 OK

---

## 5. L13.4 audit_coverage_check.py — 审计覆盖率检测

### 5.1 当前状态

- ✅ `tools/audit_coverage_check.py` 代码完成
- ✅ `tools/tests/test_audit_coverage.py` 单元测试完成
- ❌ **未集成到 post_deploy_check.py**
- ❌ **未部署到 yonaa**

### 5.2 剩余工作

| Step | 内容 | 工作量 | 优先级 |
|------|------|--------|--------|
| 5.2.1 | 集成到 `tools/post_deploy_check.py` 末尾 | 0.1d | P1 |
| 5.2.2 | 上传到 yonaa /opt/app/shared/ | 0.05d | P1 |
| 5.2.3 | 在 yonaa 跑实测 | 0.1d | P1 |

### 5.3 验收标准

- [ ] post_deploy_check.py 末尾调用 audit_coverage_check.py
- [ ] yonaa 上 `python3 audit_coverage_check.py --days 30` 输出报告
- [ ] exit code: 0=ok, 1=fail, 2=warn

---

## 6. L14 deploy_service.py (9205) — 部署编排服务

### 6.1 当前状态

- ✅ `tools/deploy_service.py` 代码完成 (11 状态机 + 后台线程)
- ✅ L11.3 二次确认 (rollback/cancel)
- ✅ `tools/deploy_service.service` systemd unit 文件
- ❌ **端口冲突**: yonaa 9205 已被 error_aggregator 占用
- ❌ **未接入真实 deploy.sh** (当前 deploy_worker 是模拟)
- ❌ **未部署到 yonaa**
- ❌ 绑定 0.0.0.0 (需改 BIND)

### 6.2 端口冲突问题

同 L13.3，9205 被 error_aggregator 占用。

**选项**:
- **A**: 使用 9215 端口 — 推荐
- **B**: 停掉 error_aggregator 释放 9205

### 6.3 核心遗留: deploy_worker 是模拟版

当前 `deploy_service.py` 的 `deploy_worker()` 只是 `time.sleep(2)` 模拟状态机推进，**没有调用 deploy.sh**。

**改造要点**:
1. deploy_worker 需调用 `bash /opt/app/shared/deploy.sh` 的各 PHASE
2. 或更简单: 调用整个 deploy.sh，monitor 其 stdout/stderr
3. 需要处理 deploy.sh 的 exit code 映射到 DeployState

### 6.4 剩余工作

| Step | 内容 | 工作量 | 优先级 |
|------|------|--------|--------|
| 6.4.1 | 确认端口 (9215 或 9205) | 需用户确认 | P1 |
| 6.4.2 | deploy_worker 改为调用真实 deploy.sh | 1d | P1 |
| 6.4.3 | 加 BIND 环境变量支持 (0.0.0.0 → 可配置) | 0.1d | P1 |
| 6.4.4 | 上传 + systemd + 启动 | 0.2d | P1 |
| 6.4.5 | 端到端测试 (staging) | 0.5d | P1 |

### 6.5 deploy_worker 改造设计

```python
def deploy_worker(version, zip_path, deployment_type="full"):
    """真实部署线程 — 调用 deploy.sh"""
    try:
        # 1. pre-check
        transition(DeployState.PRE_CHECK)
        rc = subprocess.run(
            ["bash", DEPLOY_SH, "--skip-unzip", "--version", version],
            env={**os.environ, "ZIP_PATH": zip_path, "DEPLOY_MODE": deployment_type},
            capture_output=True, text=True, timeout=600  # 10min
        )
        if rc.returncode != 0:
            raise RuntimeError(f"deploy.sh failed: {rc.stderr[-500:]}")

        transition(DeployState.DONE)
    except Exception as e:
        transition(DeployState.FAILED)
        log(f"FAILED: {e}")
    finally:
        DEPLOY_HISTORY.appendleft(dict(CURRENT_DEPLOY))
```

### 6.6 验收标准

- [ ] deploy_service 监听 9215 (BIND=172.20.59.7)
- [ ] POST /api/deploy/start 触发真实 deploy.sh
- [ ] GET /api/deploy/status 返回实时状态
- [ ] POST /api/deploy/rollback 需要 confirm=yes-i-know
- [ ] 部署失败时状态 = failed，可重试

---

## 7. L15 monitor_prod.py 演进

### 7.1 当前状态

- ⚠️ yonaa 上 `/opt/app/shared/monitor_prod.py` 是 V007.67 版 (已修复 base64，纯 HTTP)
- ❌ **未更新** L8.8 isolation_check / L13.4 audit_coverage / L15.2 post_deploy 集成
- ❌ **未集成** dbops_service / deploy_service 检查
- ❌ 源码在 `d:\filework\worktrees/release-prep\` 下未找到 (只在 yonaa 上有 V007.67 版)

### 7.2 需要新增的检查 section

| # | Section | 依赖 | 优先级 |
|---|---------|------|--------|
| L15.1 | check_config_service (9203) | config_service 部署 | P1 |
| L15.2 | check_post_deploy | post_deploy_check.py 部署到 yonaa | P1 |
| L15.3 | check_audit_coverage | audit_coverage_check.py 部署到 yonaa | P1 |
| L15.4 | check_dbops_service (9214) | dbops_service 部署 | P0 |
| L15.5 | check_deploy_service (9215) | deploy_service 部署 | P1 |
| L15.6 | check_isolation (L8.8) | core_service 新版部署 | P1 |
| L15.7 | check_nsfocus_bind | NSFOCUS-L4 服务重启 | **P0** |

### 7.3 剩余工作

| Step | 内容 | 工作量 | 优先级 |
|------|------|--------|--------|
| 7.3.1 | 找到/创建 monitor_prod.py 源码 | 0.1d | P0 |
| 7.3.2 | 加 7 个新 check section | 0.3d | P1 |
| 7.3.3 | 部署到 yonaa /opt/app/shared/ | 0.05d | P1 |
| 7.3.4 | 跑实测 (12+ sections 全 ok) | 0.1d | P1 |

### 7.4 验收标准

- [ ] monitor_prod.py 包含 12+ 检查 section
- [ ] yonaa 上跑 `python3 monitor_prod.py` 全部 ok
- [ ] NSFOCUS BIND 状态检查正常

---

## 8. L17 智能 delta 部署

### 8.1 当前状态

- ✅ `tools/manifest_utils.py` 完成 (Manifest/FileEntry/parse/generate/compute_delta/build_delta_zip/verify)
- ✅ `deploy_bundle/lib/smart_extract.sh` 完成 (delta/full/hotfix 三模式)
- ✅ `deploy_bundle/lib/sha256_compare.sh` 完成
- ✅ `deploy_bundle/deploy.sh` 已集成 delta 模式 (L174-298)
- ✅ `tools/tests/test_delta_manifest.py` 完成
- ✅ yonaa 上已部署 manifest_utils.py / smart_extract.sh / sha256_compare.sh
- ✅ yonaa 上已实测 delta_test (1048 文件扫描, 3 个 delta 文件正确)
- ❌ **生产 deploy.sh 未更新** (yonaa /opt/app/shared/deploy_prod.sh 还是 7/5 版本)
- ❌ **rebuild_zip.py 未加 --delta 选项** (打包端不支持 delta)

### 8.2 剩余工作

| Step | 内容 | 工作量 | 优先级 |
|------|------|--------|--------|
| 8.2.1 | rebuild_zip.py 加 --delta 选项 | 0.5d | P1 |
| 8.2.2 | 更新 yonaa deploy_prod.sh 集成 smart_extract | 0.3d | P1 |
| 8.2.3 | staging 端到端 delta 部署测试 | 0.5d | P1 |
| 8.2.4 | 生产首次 delta 部署验证 | 0.5d | P2 |

### 8.3 rebuild_zip.py --delta 集成

当前 rebuild_zip.py 只做全量打包。需加:

```
--delta              生成 delta zip (只含 changed files)
--prev-manifest PATH 指定上一版 MANIFEST (默认读 deploy_bundle/MANIFEST)
```

delta 打包流程:
1. 读取 prev MANIFEST
2. 扫描当前 deploy_bundle/ 生成 new MANIFEST
3. compute_delta(old, new)
4. build_delta_zip 只打包 changed files
5. 输出: delta zip (1-5MB vs 全量 80MB)

### 8.4 验收标准

- [ ] `rebuild_zip.py --delta` 生成 < 5MB 的 delta zip
- [ ] yonaa 上 delta 部署成功 (smart_extract 模式)
- [ ] delta 后跑 post_deploy_check 验证完整性
- [ ] 全量回退: `--full` 参数仍可用

---

## 9. NSFOCUS 绿盟合规 (交叉引用)

**注意**: 以下与部署基础设施强绑定，必须一起做:

| NSFOCUS 项 | 依赖的 TODO | 说明 |
|-----------|------------|------|
| **L4 BIND=172.20.59.7** | L8.8 + core_service 更新 | 重启 core_service = 同时完成 L4 + L8.8 |
| **L4 其他服务重启** | 所有服务的 BIND 环境变量 | .env_global 已部署，9200/9101/8081 需深夜重启 |
| **L7.f SSH 密码** | 无代码依赖 | 纯运维，需确认 SSH key |
| **L6.g iptables** | 无代码依赖 | 纯运维，需确认 agent/jumper IP |

**关键决策**: L4 服务重启是最紧急的 NSFOCUS 修复，建议:
1. 先在 staging 上验证 BIND=172.20.59.7
2. 深夜 0-3 点执行核心服务重启
3. 重启后跑 monitor_prod.py 验证

---

## 10. 所有服务 BIND 支持现状

| 服务 | 代码已有 BIND | yonaa 实际 BIND | 需改 |
|------|-------------|----------------|------|
| core_service (9200) | ✅ L39 | 0.0.0.0 | 重启 |
| log_service (9101) | ✅ L43 | 0.0.0.0 | 重启 |
| observability (9201) | ⚠️ 未确认 | 0.0.0.0 | 需加 BIND |
| config_service (9203) | ⚠️ 未确认 | 0.0.0.0 | 需加 BIND |
| dbops_service (9204) | ❌ 硬编码 0.0.0.0 | 0.0.0.0 | 需改代码 |
| deploy_service (9205) | ❌ 硬编码 0.0.0.0 | 0.0.0.0 | 需改代码 |
| ops_scheduler (9202) | ⚠️ 未确认 | 0.0.0.0 | 需确认 |
| error_aggregator (9206) | ⚠️ 未确认 | 0.0.0.0 | 需确认 |
| slo_service (9207) | ⚠️ 未确认 | 0.0.0.0 | 需确认 |
| health_service (9208) | ⚠️ 未确认 | 0.0.0.0 | 需确认 |

**L4 修复前提**: 所有服务代码需加 `BIND = os.environ.get("*_BIND", "0.0.0.0")` + `.env_global` 已有 13 个 export。

---

## 11. 实施优先级排序

### Phase 1: NSFOCUS 紧急 (本周)

| # | 任务 | 风险 | 耗时 |
|---|------|------|------|
| 1.1 | 确认所有服务的 BIND 代码支持 | 低 | 0.5d |
| 1.2 | 修复 dbops_service / deploy_service 的 0.0.0.0 硬编码 | 低 | 0.1d |
| 1.3 | staging 服务重启 (19101/13011/18081/19200) | 低 | 0.2d |
| 1.4 | 深夜核心服务重启 (9200/9101/8081/3011) | 🔴 高 | 0.5d |

### Phase 2: 基础设施部署 (本周-下周)

| # | 任务 | 依赖 | 耗时 |
|---|------|------|------|
| 2.1 | L8.6 unzip_safe 部署 + deploy.sh 集成 | 无 | 0.2d |
| 2.2 | L13.3 dbops_service 部署 (确认端口) | 端口确认 | 0.3d |
| 2.3 | L13.4 audit_coverage_check 部署 + post_deploy 集成 | 无 | 0.2d |
| 2.4 | L14 deploy_service 改造 (真实 deploy.sh) | 端口确认 | 1.5d |
| 2.5 | L15 monitor_prod.py 演进 (7 个新 section) | 2.1-2.4 | 0.4d |

### Phase 3: Delta 部署能力 (下周)

| # | 任务 | 依赖 | 耗时 |
|---|------|------|------|
| 3.1 | rebuild_zip.py --delta 集成 | 无 | 0.5d |
| 3.2 | 更新 yonaa deploy_prod.sh | 3.1 | 0.3d |
| 3.3 | staging 端到端 delta 部署测试 | 3.1+3.2 | 0.5d |

### Phase 4: 远期 (本月)

| # | 任务 | 依赖 | 耗时 |
|---|------|------|------|
| 4.1 | L12 remote_helper.py session 模式 | Phase 2 | 0.5d |
| 4.2 | NSFOCUS L7.f SSH 密码修复 | 确认 key | 0.2d |
| 4.3 | NSFOCUS L6.g iptables 规则 | 确认 IP | 0.5d |
| 4.4 | 生产首次 delta 部署 | Phase 3 | 0.5d |

---

## 12. 待用户确认的决策

| # | 问题 | 选项 | 建议 |
|---|------|------|------|
| Q1 | dbops_service 端口 | A: 9214 (新) / B: 9204 (需停 error_aggregator) | A |
| Q2 | deploy_service 端口 | A: 9215 (新) / B: 9205 (需停 error_aggregator) | A |
| Q3 | L4 核心服务重启时间 | 深夜 0-3 点 / 其他 | 深夜 |
| Q4 | L14 deploy_service 是否接入真实 deploy.sh | 是 (生产级) / 否 (先做 API 骨架) | 先骨架后接入 |
| Q5 | L7.f SSH key 是否已配置 | 是 / 否 / 不确定 | 需确认 |
| Q6 | Phase 1-2 是否可并行 | staging 先做 / 全部串行 | staging 先做 |

---

## 13. 文件结构汇总

### 已有文件 (代码已写，待部署)

```
tools/
├── core_service.py            # ✅ 已含 L8.8 + L12
├── unzip_safe.py              # ✅ 已写
├── audit_coverage_check.py    # ✅ 已写
├── audit_recovery.py          # ✅ 已写
├── dbops_service.py           # ✅ 已写 (需改 BIND + 端口)
├── deploy_service.py          # ⚠️ 需改造 deploy_worker
├── manifest_utils.py          # ✅ 已写
├── post_deploy_check.py       # ⚠️ 需加 L13.4 集成
├── rebuild_zip.py             # ⚠️ 需加 --delta
├── monitor_prod.py            # ❌ 源码缺失 (只有 yonaa 上的 V007.67)
└── tests/
    ├── test_unzip_safe.py     # ✅
    ├── test_audit_coverage.py # ✅
    ├── test_delta_manifest.py # ✅
    └── test_deploy_service.py # ⚠️ skip

deploy_bundle/
├── deploy.sh                  # ✅ 已含 L17 delta 模式
└── lib/
    ├── smart_extract.sh       # ✅
    ├── sha256_compare.sh      # ✅
    ├── common.sh              # ✅
    └── check_deploy_health.sh # ✅
```

### 需修改的文件

```
tools/
├── dbops_service.py           # 加 BIND + 改端口
├── deploy_service.py          # 加 BIND + 改端口 + deploy_worker 真实化
├── post_deploy_check.py       # 加 L13.4 audit_coverage 集成
├── rebuild_zip.py             # 加 --delta 选项
└── remote_helper.py           # 加 RemoteSession (L12)

deploy_bundle/
└── deploy.sh                  # 加 L8.6 unzip_safe 调用
```

---

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-07-14 | AI Assistant | 初版: 基于 TODO_LONGTERM.md + NSFOCUS 实测 + delta 实测的全面 spec |
