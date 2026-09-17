# 部署拓扑通用化 — symlink + namespace package 双发的踩坑

> **问题**: staging 部署反复栽在"路径解析"上，同一类问题发生 ≥5 次
> **解决方案**: DeployTarget + PathResolver + ResourceType 三层抽象
> **关联**: [retrospective 2026-09-13](../retrospectives/2026-09-13-deploy-topology-generalization.md)
> **关键工具**: [tools/deploy_upload.py](../../tools/deploy_upload.py) / [tools/lib/deploy_topology.py](../../tools/lib/deploy_topology.py) / [tools/lib/path_resolvers.py](../../tools/lib/path_resolvers.py)

---

## 问题描述

staging 后端 cwd = `/opt/app/staging/deploy/v1789297457_staging_spec22`，`meta/` 是 symlink → current。

`meta/` 目录下只有 spec22 修改过的子集文件：
- `meta/api/bo_api.py`（新版）
- `meta/core/{models, models_enums, yaml_loader}.py`（新版）
- `meta/schemas/{user, _standard_actions}.yaml`
- **没有** `meta/core/bo_framework.py`（顶层 core/ 才有）

Python `from meta.api.bo_api` 实际加载 `meta/api/bo_api.py`（namespace package 解析），但 `meta.api.bo_api` 里 `from meta.core.bo_framework` 找不到 — 因为 meta/core/ 没有 bo_framework.py。

但 backend 通过 **lazy route 注册 + lazy import** 规避了 cold-start 失败 — 所以 `/state-transition-actions` 端点仍能返回数据（HTTP 401 表示 endpoint 已注册）。

**症状**: spec22 路由在前端表现奇怪（虽然 200，但行为可能 stale）。

---

## 解决方案

### 双发策略

每次上传 spec22 修改的文件时，**必须同时上传到两个路径**：
1. `{deploy_root}/meta/X/Y` — 走 namespace package 解析，加载 spec22 补丁
2. `{deploy_root}/X/Y` — 提供完整的 core 包（bo_framework 等未修改文件）

### 抽象化

把"双发"封装到通用框架：

```python
# tools/lib/path_resolvers.py
class SymlinkNamespacePackageResolver(PathResolver):
    """staging 关键: 双发 meta/X/Y + X/Y"""
    DOUBLE_PATH_PREFIXES = (
        "meta/api/", "meta/core/", "meta/services/", "meta/blueprints/",
    )
    YAML_DOUBLE_PATH_PREFIXES = ("meta/schemas/", "meta/config/")

    def resolve(self, deploy_root, local_path, resource_type, override):
        rel = self._relative_to_repo(local_path)
        if rel.startswith("meta/"):
            stripped = rel[len("meta/"):]
        else:
            stripped = rel

        if resource_type == "python_module" and self._is_double_path(rel):
            return [
                f"{deploy_root.rstrip('/')}/meta/{stripped}",
                f"{deploy_root.rstrip('/')}/{stripped}",
            ]
        # ... yaml_config / single-path
```

### 验证

```bash
# 解析预览
python tools/deploy_upload.py --target staging resolve meta/api/bo_api.py
# → /opt/app/staging/deploy/current/meta/api/bo_api.py
# → /opt/app/staging/deploy/current/api/bo_api.py

# 上传 + md5 验证
python tools/deploy_upload.py --target staging upload meta/api/bo_api.py
# [OK remote_upload] md5=match /opt/app/staging/deploy/current/meta/api/bo_api.py
# [OK remote_upload] md5=match /opt/app/staging/deploy/current/api/bo_api.py

# Python introspect (核心: 看 Python 实际加载的模块路径)
python tools/deploy_upload.py --target staging healthcheck --introspect \
    --module meta.api.bo_api --module meta.core.models
```

---

## 经验总结

### 5 条铁律

1. **md5 自证永远不够**。md5 一致 ≠ Python 加载的是新代码（参见 [9-05 复盘 §5](../retrospectives/2026-09-05-staging-meta-shadow-tree.md#5-证据陷阱清单-为什么每一步都像成功)）。
2. **必须有运行时 introspect**。`python -c "import X; print(X.__file__)"` 是金标准 — 看 Python 实际加载的路径，不是"写入文件"的路径。
3. **抽象优于硬编码**。"symlink + namespace package 双发"是特例，不是通则；用 PathResolver + 配置可以适配所有场景。
4. **新环境接入零代码改动**。加 production / preview / k8s pod 部署目标 = 在 YAML 加一行 + (可选) 加一个 Resolver 子类。
5. **md5 / py_compile / dev-login 三连不构成送达证明**。必须有"运行中进程可见的行为差异"。

### 反例 (不要这么做)

```bash
# ❌ 只传到 meta/X/Y: backend 通过 lazy import 暂时能跑, 但 cold-start 会失败
scp meta/api/bo_api.py root@staging:/opt/app/staging/deploy/current/meta/api/bo_api.py

# ❌ 只传到顶层 X/Y: 顶层 X/Y 没动 (bo_framework 还是顶层版本), meta 包覆盖不到
scp meta/api/bo_api.py root@staging:/opt/app/staging/deploy/current/api/bo_api.py

# ❌ 验证 = md5:
md5sum meta/api/bo_api.py /opt/app/staging/deploy/current/meta/api/bo_api.py  # 一致 ≠ 进程加载

# ✅ 正确做法: deploy_upload.py 双发 + introspect 验证
python tools/deploy_upload.py --target staging upload meta/api/bo_api.py
python tools/deploy_upload.py --target staging healthcheck --introspect --module meta.api.bo_api
```

---

## 反复发生的家族

| 日期 | 症状 | 当时定位 | 现在怎么防 |
|---|---|---|---|
| 2026-07-04 | dev 修好 prod 没修 | 部署链未端到端 | deploy_topology 显式 --target 区分 |
| 2026-08-29 | 后端进程跑旧代码 | 重启未生效 | healthcheck --introspect |
| 2026-09-03 | 前端跑旧 dist | dist 产物送达 | verify --remote 自动 |
| 2026-09-03 | `no such table: org_members` | 相对路径 DB | 抽象 deploy_root，不写死相对路径 |
| 2026-09-05 | staging 行为零变化 | meta 包解析路径 | 双发（已修），但需 deploy_topology 抽象 |
| **2026-09-13** | **spec22 路由 `data: []`** | **顶层 vs meta 双轨** | **deploy_topology 框架 + introspect** |

---

## 相关文档

- [retrospective 2026-09-13-deploy-topology-generalization.md](../retrospectives/2026-09-13-deploy-topology-generalization.md) — 完整复盘
- [retrospective 2026-09-05-staging-meta-shadow-tree.md](../retrospectives/2026-09-05-staging-meta-shadow-tree.md) — 前置复盘
- [staging-runbook.md §3.4](../staging-runbook.md#34-通用部署拓扑-deploy_uploadpy--2026-09-13-推荐) — 使用 SOP
- [STAGING_GUIDE.md §1.1b](../STAGING_GUIDE.md#11b-通用部署拓扑-cli-推荐--单文件上传-2026-09-13-) — 速查入口

## 相关代码

| 文件 | 用途 |
|------|------|
| [tools/deploy_upload.py](../../tools/deploy_upload.py) | CLI 入口 (resolve/upload/verify/healthcheck) |
| [tools/lib/deploy_topology.py](../../tools/lib/deploy_topology.py) | DeployTarget 抽象 |
| [tools/lib/path_resolvers.py](../../tools/lib/path_resolvers.py) | 4 个 PathResolver |
| [tools/lib/__init__.py](../../tools/lib/__init__.py) | package marker |
| [tools/config/deploy_topology.yaml](../../tools/config/deploy_topology.yaml) | 声明式配置 (staging/production/dev/preview) |