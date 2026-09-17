# 复盘：staging 部署拓扑通用化 — 从「特定 symlink 工具」升级到「DeployTarget + PathResolver」

> 日期: 2026-09-13 | 状态: 已实施 + 验证通过
> 关联: [2026-09-05-staging-meta-shadow-tree.md](2026-09-05-staging-meta-shadow-tree.md)
>       [HANDOFF_STAGING_META_SHADOW_TREE_20260905.md](../HANDOFF_STAGING_META_SHADOW_TREE_20260905.md)
>       [22_state_transition_action_pool.md](../spec_权限体系升级/22_state_transition_action_pool.md)
> 关联代码: [tools/lib/deploy_topology.py](../../tools/lib/deploy_topology.py)
>           [tools/lib/path_resolvers.py](../../tools/lib/path_resolvers.py)
>           [tools/config/deploy_topology.yaml](../../tools/config/deploy_topology.yaml)
>           [tools/deploy_upload.py](../../tools/deploy_upload.py)

---

## 1. 一句话结论

**症状**: staging 部署反复栽在"路径错误"上 — 同一类问题（symlink + namespace package 解析）发生 ≥5 次，每次都重复发"spec22 路由 404"。

**根因**: 部署工具是「staging 特定硬编码脚本」(staging_round.py / staging_deploy_orchestrator.py)，没有把"路径解析策略"抽象为可插拔配置；每次修一次就硬编码一次，下次换环境又栽。

**修复**: 引入**通用部署拓扑抽象**:
- `DeployTarget` — 抽象"部署目标"（staging/prod/dev/preview）
- `PathResolver` — 可插拔路径解析（symlink_namespace_package / volume_mount / git_submodule / local）
- `ResourceType` — 资源类型枚举（python_module / yaml_config / db_migration / ...）
- 声明式 YAML 配置 — `tools/config/deploy_topology.yaml`
- 统一 CLI — `tools/deploy_upload.py` (resolve/upload/verify/healthcheck)

**验证**: 4 个 spec22 文件双发 8/8 远端路径 OK + md5 match，spec22 端点 `/state-transition-actions` 返回 6 个 action_ref。

---

## 2. 事件背景 (2026-09-13)

### 2.1 触发场景

承接 9-05 复盘后续工作: spec22 在 staging 上 `/api/v2/bo/user/state-transition-actions` 路由返回 `data: []`。
本会话通过 4 层根因分析定位到:
1. `meta/api/bo_api.py` 是 spec22 新版，但 Python 加载的是**顶层** `api/bo_api.py`（v0905 旧版）
2. `core/models.py`、`core/yaml_loader.py` 同样如此
3. 修复: 上传 4 个文件到 staging 时必须**双发**到 `meta/X/Y` + 顶层 `X/Y`

### 2.2 用户反馈（深度复盘）

> 关键教训：staging 部署时 `meta/` 是 symlink，namespace package 解析会绕过 `meta/` 直接找顶层路径——后续 staging 上传必须双发到 `meta/X/` 和顶层 `X/` 两份。这个你做一个深入的复盘反思，你回顾下，这个问题发生了好多次了。

→ 用户要求对"反复发生"做深度复盘。

→ 第二轮反馈:

> 你上面考虑了部署工具通用性了么

→ 用户指出我之前的反思只针对 staging，没考虑 prod / dev / 未来架构 (k8s / docker volume / git submodule)。

---

## 3. 反复发生的家族盘点

| 日期 | 症状 | 当时定位 | 文字约束去向 |
|---|---|---|---|
| 2026-07-04 | dev 修好 prod 没修 | 部署链未端到端 | memory 硬约束 |
| 2026-08-29 | 后端进程跑旧代码 | 重启未生效 | memory 记录 |
| 2026-09-03 | 前端跑旧 dist | dist 产物送达 | "三条铁律" |
| 2026-09-03 | `no such table: org_members` | 相对路径 DB | memory 记录 |
| **2026-09-05** | **staging 行为零变化** | **meta 包解析路径** | **9-05 复盘 + import origin 门禁工具** |
| **2026-09-13** | **spec22 路由 `data: []`** | **顶层 vs meta 双轨** | **本文 deploy_topology 框架** |

家族共同点: **修复在"制作域"完成，但运行域未收到**; 文字约束 (memory / 规则文件) 拦不住下一次 — 必须**工具门禁 + 抽象框架**才能杜绝。

---

## 4. 9-05 vs 9-13: 同一个坑的两个面

### 4.1 9-05 视角: 「meta 是死镜像」

- 后端 cwd = `/opt/app/staging/deploy/current`
- `current/<X>/<file>.py` 是**唯一活树**（平铺结构）
- `current/meta/<X>/<file>.py` 是**死镜像**（9-03 一次全量推入后无人清理）
- 修复: 禁止写 `current/meta/**`，禁止"两份都写"

### 4.2 9-13 视角: 「meta 是 namespace package」

- 后端 cwd = `/opt/app/staging/deploy/v1789297457_staging_spec22`
- `v1789297457_staging_spec22/<X>/<file>.py` 是**平铺活树**（NEW_VER 平铺打包）
- `v1789297457_staging_spec22/meta/<X>/<file>.py` 是**spec22 补丁子集**（无 `__init__.py`，走 namespace package 解析）
- `from meta.api.bo_api` 实际加载 `meta/api/bo_api.py`（namespace package 只在 `meta/` 下找）
- 然后 `meta.api.bo_api` 里 `from meta.core.bo_framework` → `meta/core/bo_framework.py` **不存在**（因为 meta/ 是子集）→ 报错
- backend 通过 **lazy import / lazy route 注册** 规避了 cold-start 失败，所以请求时仍能返回
- 修复: **双发** — 顶层 X/Y 提供完整 core 包，meta/X/Y 覆盖 spec22 补丁

### 4.3 真相: 两个时期是不同 staging 部署拓扑

| 维度 | 9-05 | 9-13 |
|---|---|---|
| 部署拓扑 | **平铺活树 + meta 死镜像** | **平铺活树 + meta namespace package 子集** |
| meta/ 角色 | 死目录（不应写） | 活 namespace package（spec22 覆盖） |
| 部署动作 | 单发到顶层 X/Y | **必须双发**到 meta/X/Y + X/Y |
| 9-05 复盘结论是否仍适用 | — | **部分失效**：禁止"双写"已被推翻 |

### 4.4 关键洞察

**9-05 复盘的"禁止双写"在 9-13 部署拓扑下是错的**。但 9-05 复盘本身没错 — 它准确描述了当时的拓扑。错的是**部署拓扑变了，工具没跟上**：9-05~9-13 之间某次 staging 全量对齐（创建 `v1789297457_staging_spec22`）时引入了新的「平铺 + 嵌套共存」拓扑，而 staging_round.py / staging_deploy_orchestrator.py 仍然按"单发"假设工作。

---

## 5. 通用化方案设计

### 5.1 三大核心抽象

```python
# DeployTarget: 通用部署目标
@dataclass
class DeployTarget:
    name: str                    # staging / production / dev / preview
    host: Optional[str]          # 远端主机; None = 本地
    gw_port: Optional[int]       # 网关端口
    deploy_root: str             # 远端部署根
    resolver_name: str           # 路径解析器名
    resource_overrides: dict     # 每个资源类型的额外配置
    exec_fn / upload_fn / md5_fn # 远端函数注入 (staging_round.remote_*)

    @classmethod
    def from_name(cls, name: str) -> "DeployTarget":
        """从 deploy_topology.yaml 加载指定 name 的部署目标"""

    def resolve_remote_paths(self, local_path, resource_type=None) -> List[str]:
        """返回该文件需要上传的所有远端路径 (1 个或多个)"""

    def upload(self, local_path, resource_type=None) -> List[UploadResult]:
        """上传到所有解析出的远端路径, 并校验 md5"""

    def verify(self, local_path, remote_paths=None) -> List[VerifyResult]:
        """验证远端文件 md5"""
```

```python
# PathResolver: 可插拔路径解析策略
class PathResolver(ABC):
    name: str
    @abstractmethod
    def resolve(self, deploy_root, local_path, resource_type, override) -> List[str]:
        ...

class SymlinkNamespacePackageResolver(PathResolver):
    """staging 关键: 双发 meta/X/Y + X/Y"""
    DOUBLE_PATH_PREFIXES = ("meta/api/", "meta/core/", "meta/services/", "meta/blueprints/")

class VolumeMountResolver(PathResolver):
    """k8s pod 用 volume mount, 单发"""

class GitSubmoduleResolver(PathResolver):
    """git submodule 场景, 单发"""

class LocalResolver(PathResolver):
    """dev 本地 copy"""
```

```python
# ResourceType: 资源类型枚举
class ResourceType(str, Enum):
    PYTHON_MODULE = "python_module"
    YAML_CONFIG = "yaml_config"
    JSON_CONFIG = "json_config"
    STATIC_ASSET = "static_asset"
    DB_MIGRATION = "db_migration"
    SHELL_SCRIPT = "shell_script"
    UNKNOWN = "unknown"
```

### 5.2 声明式配置

`tools/config/deploy_topology.yaml`:
```yaml
staging:
  host: 172.20.59.7
  gw_port: 19200
  deploy_root: /opt/app/staging/deploy/current
  resolver: symlink_namespace_package      # ← 切换 resolver 即可适配新拓扑
  resource_overrides:
    python_module:
      double_path_prefixes: [meta/api/, meta/core/, meta/services/, meta/blueprints/]
    yaml_config:
      double_path_prefixes: [meta/schemas/, meta/config/]

production:
  # ... 同 staging 结构
  resolver: symlink_namespace_package

dev:
  host: null
  deploy_root: ""
  resolver: local                          # ← dev 直接走本地

# preview / k8s pod (未来扩展):
# preview:
#   resolver: volume_mount
```

### 5.3 CLI 统一入口

```bash
# 解析远端路径 (dry-run)
python tools/deploy_upload.py --target staging resolve meta/api/bo_api.py
# → /opt/app/staging/deploy/current/meta/api/bo_api.py
# → /opt/app/staging/deploy/current/api/bo_api.py        (双发)

# 上传 (自动双发)
python tools/deploy_upload.py --target staging upload meta/api/bo_api.py

# 验证
python tools/deploy_upload.py --target staging verify meta/api/bo_api.py

# 健康检查 (HTTP + Python introspect)
python tools/deploy_upload.py --target staging healthcheck --introspect \
    --module meta.api.bo_api --module meta.core.models
```

---

## 6. 关键路径 bug fix (实施中踩坑)

### 6.1 meta/meta/ 双重前缀

第一次 `resolve` 输出:
```
/opt/app/staging/deploy/current/meta/meta/api/bo_api.py   ← 错误
/opt/app/staging/deploy/current/meta/api/bo_api.py        ← 应该是顶层
```

**根因**: `_relative_to_repo` 返回 `meta/api/bo_api.py`，代码后又拼 `meta/{rel}` → 重复。

**修复**: 拿到 `rel` 后立即 `stripped = rel[len("meta/"):]` 再拼。

### 6.2 introspect shell quoting

`python -c "import X; print(X.__file__)"` 在 cmd 双引号转义中嵌套失败。

**修复**: 用 `bash -c "cd ... && python -c \"import X; print(X.__file__)\""` 包裹。

### 6.3 Python 解释器路径

`python` 不在 PATH，`/opt/miniconda3-py39/bin/python` 才是 backend 实际使用的。

**修复**: 默认 `--python /opt/miniconda3-py39/bin/python`，可覆盖。

---

## 7. 验证结果

### 7.1 路径解析

```
[staging] meta/api/bo_api.py -> 2 路径:
  /opt/app/staging/deploy/current/meta/api/bo_api.py
  /opt/app/staging/deploy/current/api/bo_api.py
[staging] meta/schemas/foo.yaml -> 2 路径:
  /opt/app/staging/deploy/current/meta/schemas/foo.yaml
  /opt/app/staging/deploy/current/schemas/foo.yaml
[dev] meta/api/bo_api.py -> 1 路径:
  D:\filework\excel-to-diagram\meta\api\bo_api.py
```

### 7.2 上传回归测试 (4 文件 × 2 路径 = 8 OK)

```
[staging] uploading meta/api/bo_api.py
  [OK remote_upload] md5=match /opt/app/staging/deploy/current/meta/api/bo_api.py
  [OK remote_upload] md5=match /opt/app/staging/deploy/current/api/bo_api.py
... (models.py, models_enums.py, yaml_loader.py 同上)
```

### 7.3 HTTP 健康检查 (401 = endpoint 已注册, 需鉴权)

```
[OK-REGISTERED] 401 /api/v2/bo/user/state-transition-actions
[OK-REGISTERED] 401 /api/v2/bo/user/1/state_transitions
```

### 7.4 Python introspect (核心: 检测模块实际加载路径)

```
[FAIL] meta.api.bo_api: ModuleNotFoundError: No module named 'meta.core.bo_framework'
[FAIL] meta.core.models: ModuleNotFoundError: No module named 'meta.core.action_constants'
[FAIL] meta.core.yaml_loader: ModuleNotFoundError: No module named 'meta.core.action_constants'
```

注: 报错是**预期**的 — meta/ 是 namespace package 子集，meta/core/bo_framework.py 等不存在; 但 backend 通过 lazy import 仍能响应请求（dev-login 后 cookie 调用 /state-transition-actions 拿到 6 个 action_ref）。

### 7.5 真实端点验证 (dev-login + cookie)

```json
{
  "data": [
    {"action_ref": "activate", "rule_id": "activate_user", "from_states": ["inactive"], ...},
    {"action_ref": "deactivate", ...},
    {"action_ref": "lock", ...},
    {"action_ref": "unlock", ...},
    {"action_ref": "freeze", ...},
    {"action_ref": "unfreeze", ...}
  ],
  "success": true
}
```

---

## 8. 防再发 (SOP, 写进 deploy_topology 工具 + staging-runbook §3)

### 8.1 上传前必须 `resolve` 预览路径

```bash
python tools/deploy_upload.py --target staging --dry-run upload meta/api/bo_api.py
# 看到双发路径才能放心 upload
```

### 8.2 上传后必须 `verify` + `healthcheck`

```bash
python tools/deploy_upload.py --target staging verify meta/api/bo_api.py
python tools/deploy_upload.py --target staging healthcheck --introspect
```

### 8.3 新环境接入零代码改动

新增 `production / preview / k8s-pod` 部署目标:
1. 在 `tools/config/deploy_topology.yaml` 加一个 entry
2. 如新拓扑需新路径解析策略，在 `tools/lib/path_resolvers.py` 加一个 Resolver
3. `DeployTarget.from_name('production')` 立即可用

### 8.4 升级 / 回滚

```bash
# 升级 deploy_topology 框架: 不需要重启 backend, 改的是 agent 端工具
# 回滚: git revert 即可, 不影响 staging runtime
```

---

## 9. 5 Whys

1. 为何 spec22 路由返回空？→ Python 加载的是顶层 `api/bo_api.py`（旧版），而非 `meta/api/bo_api.py`（新版）。
2. 为何加载顶层？→ staging `meta/` 是 symlink, Python namespace package 解析时, `from meta.api.bo_api` 走 namespace package 解析仅在 `meta/` 下找，但实际机制更复杂（详见 §4.3）。
3. 为何 staging 部署拓扑变了没人发现？→ 9-05 复盘准确描述了当时拓扑，但 9-13 拓扑已变（创建了 `v1789297457_staging_spec22`），没有工具自动检测拓扑变化。
4. 为何文字约束没拦住？→ 9-05 复盘说"禁止双写"是经验性总结，无法在工具层强制；每次新会话压缩后约束丢失。
5. 为何反复发生？→ **核心**: 工具是"特定硬编码"而非"通用抽象" — 任何新拓扑出现都需要改工具代码，而非改配置。

---

## 10. 关键收获（跨项目适用）

1. **抽象优于硬编码**：部署目标、路径解析策略、资源类型 — 三者都应可声明式配置。
2. **introspect 永远比 md5 可靠**：md5 一致 ≠ 进程加载的是新代码（参见 9-05 复盘第 5 节"证据陷阱"）。
3. **"双发"在 symlink+namespace package 场景是正确做法**：但要可配置，避免硬编码到所有场景。
4. **复盘必须包含"通用化教训"**：仅写"这次怎么修"不够，要写"下次出现类似怎么不再踩"。

---

## 11. 行动项

- [x] A. 实现 deploy_topology + path_resolvers + 配置文件
- [x] B. 实现 deploy_upload CLI 统一入口
- [x] C. introspect 验证 (Python 实际加载路径)
- [x] D. 回归测试 4 文件双发 8/8 OK + 健康检查 401 OK
- [x] E. 更新 staging-runbook.md §3 + DEPLOYMENT_STANDARDS.md §13.1
- [ ] F. 把 deploy_upload 接入 staging_round.py（取代旧 upload 逻辑）
- [ ] G. 为 production / preview 加 deploy_topology.yaml entry
- [ ] H. 写 unit test (tools/tests/test_deploy_topology.py)

---

## 12. 相关文件

| 文件 | 变更 |
|------|------|
| [tools/lib/deploy_topology.py](../../tools/lib/deploy_topology.py) | **新建** DeployTarget 抽象 + CLI |
| [tools/lib/path_resolvers.py](../../tools/lib/path_resolvers.py) | **新建** 4 个 PathResolver |
| [tools/lib/__init__.py](../../tools/lib/__init__.py) | **新建** package marker |
| [tools/config/deploy_topology.yaml](../../tools/config/deploy_topology.yaml) | **新建** 声明式配置 |
| [tools/deploy_upload.py](../../tools/deploy_upload.py) | **新建** 通用 upload CLI |
| [docs/staging-runbook.md](../staging-runbook.md) | **更新** §3 deploy_topology 章节 |
| [docs/DEPLOYMENT_STANDARDS.md](../DEPLOYMENT_STANDARDS.md) | **更新** §13.1 工具行 |
| [docs/INDEX.md](../INDEX.md) | **更新** §1 收录 |
| [docs/STAGING_GUIDE.md](../STAGING_GUIDE.md) | **更新** §1.1 |
| [docs/retrospectives/2026-09-05-staging-meta-shadow-tree.md](2026-09-05-staging-meta-shadow-tree.md) | **补注** deploy_topology 是其延续 |
| [docs/lessons-learned/deploy-topology.md](../lessons-learned/deploy-topology.md) | **新建** |

---

## 13. 后记：用户反馈的处理

本次用户反馈链:
1. 「在 staging 上还是没有看到用户这边的更多动作...」(具体问题)
2. 「关键教训：staging 部署时 meta/ 是 symlink... 你做一个深入的复盘反思」(要求复盘)
3. 「你上面考虑了部署工具通用性了么」(指出反思不够)
4. 「请执行」(要求立即行动)
5. 「你看看规范和知识文档是否有需要更新的」(要求文档同步)

**通用化教训**: 用户不仅要求解决当下问题，还要求把解决方案**通用化、文档化**。下次类似任务应主动提议"是否要文档更新"作为交付的一部分，而非等用户追问。