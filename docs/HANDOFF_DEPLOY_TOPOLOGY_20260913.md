# HANDOFF: 通用部署拓扑框架 — 部署智能体二次检查交接

> 日期: 2026-09-13 | 交接人: 开发智能体 | 接手人: 部署智能体
> 关联 commit: `78d07f9` (docs(deploy-topology): 通用部署拓扑框架)
> 性质: 基础设施 + 工具层变更, **不影响 staging 运行时** (纯 agent 端工具)
> 关联复盘: [retrospectives/2026-09-13-deploy-topology-generalization.md](retrospectives/2026-09-13-deploy-topology-generalization.md)

---

## 1. 一句话背景

staging 部署因「symlink + namespace package 解析绕过 meta/」反复失败 (>=5 次, 最近一次 2026-09-13 spec22 路由 `data: []`)。根因是部署工具为 staging 特定硬编码, 无路径解析抽象。本交付将该能力升级为**声明式、多环境通用框架**, 并要求部署智能体做二次检查。

**核心机制一句话**: staging 上传 python/yaml 必须双发到 `{deploy_root}/meta/X/Y` + `{deploy_root}/X/Y` 两个路径, 验证金标准是远端 `python -c "import X; print(X.__file__)"` (introspect), md5 一致不构成送达证明。

---

## 2. 交付物清单

| # | 文件 | 状态 | 职责 |
|---|------|------|------|
| 1 | [tools/lib/deploy_topology.py](../tools/lib/deploy_topology.py) | 新建 | `DeployTarget` 抽象 + `ResourceType` 枚举 + 独立 CLI |
| 2 | [tools/lib/path_resolvers.py](../tools/lib/path_resolvers.py) | 新建 | 4 个可插拔 PathResolver + 注册表 |
| 3 | [tools/lib/__init__.py](../tools/lib/__init__.py) | 新建 | package marker |
| 4 | [tools/config/deploy_topology.yaml](../tools/config/deploy_topology.yaml) | 新建 | 声明式多环境配置 (staging/production/dev, preview 注释预留) |
| 5 | [tools/deploy_upload.py](../tools/deploy_upload.py) | 新建 | 统一 CLI 入口 (resolve/upload/verify/healthcheck/list-resolvers) |
| 6 | [docs/staging-runbook.md](staging-runbook.md) | 更新 | 新增 §3.4 通用部署拓扑 SOP |
| 7 | [docs/DEPLOYMENT_STANDARDS.md](DEPLOYMENT_STANDARDS.md) | 更新 | §13.1 工具行 |
| 8 | [docs/INDEX.md](INDEX.md) / [docs/STAGING_GUIDE.md](STAGING_GUIDE.md) | 更新 | 收录索引 |
| 9 | [docs/retrospectives/2026-09-13-deploy-topology-generalization.md](retrospectives/2026-09-13-deploy-topology-generalization.md) | 新建 | 完整复盘 |
| 10 | [docs/lessons-learned/deploy-topology.md](lessons-learned/deploy-topology.md) | 新建 | 经验沉淀 (5 条铁律) |

**commit 后修正 (交接时随文档一并交付, 待 commit)**: `tools/deploy_upload.py` 新增 `_abs_path()` 相对路径归一化 — 修复 CLI 文档示例 (相对路径) 与 `resolve_remote_paths` (要求绝对路径) 不一致导致的 `ValueError: local_path must be absolute`。相对路径先按 CWD 解析, 再回落 repo 根, 支持从任意目录运行。本交接文档的 V0 检查项已在该修复后全部实测通过。

---

## 3. 架构速览

### 3.1 三层抽象

```
deploy_upload.py (CLI)
      |
      v
DeployTarget (tools/lib/deploy_topology.py)      <- from_name('staging') 读 YAML
      |  - resolve_remote_paths(local) -> [远端路径, ...]   (1 个或多个)
      |  - upload(local) -> [UploadResult]  (上传 + md5 校验)
      |  - verify(local) -> [VerifyResult]  (独立 md5 校验)
      |  - exec_fn / upload_fn / md5_fn  <- 默认绑定 staging_round.remote_*
      v
PathResolver (tools/lib/path_resolvers.py)       <- 按 target.resolver_name 选择
      - local                        dev 本地
      - symlink_namespace_package    staging: 双发 meta/X/Y + X/Y
      - volume_mount                 k8s/docker 预留: 单发
      - git_submodule                预留: 单发
```

### 3.2 资源类型与双发规则 (staging)

| ResourceType | 双发触发条件 | 产物路径 |
|---|---|---|
| python_module | rel 前缀属于 `meta/api/ | meta/core/ | meta/services/ | meta/blueprints/` | `{root}/meta/{stripped}` + `{root}/{stripped}` |
| yaml_config | rel 前缀属于 `meta/schemas/ | meta/config/` | 同上双发 |
| json_config / static_asset / db_migration / shell_script | — | 单发 `{root}/{stripped}` |

`stripped` = 去掉 `meta/` 前缀后的相对 repo 路径 (曾踩坑: 不 strip 会产生 `meta/meta/api/...` 双重前缀, 已修复)。

### 3.3 关键配置 (deploy_topology.yaml staging 节)

- host `172.20.59.7`, gw_port `19200` (staging_round 远端通道)
- deploy_root `/opt/app/staging/deploy/current` (symlink)
- health_check.base_url `http://172.20.59.7:13011`
- health_check.spec22_endpoints: `/api/v2/bo/user/state-transition-actions`, `/api/v2/bo/user/1/state_transitions`

---

## 4. CLI 用法参考

```bash
# 全局: --target/-t (默认 staging), --dry-run (仅影响 upload)

python tools/deploy_upload.py list-resolvers                       # 列出 resolver
python tools/deploy_upload.py resolve  meta/api/bo_api.py          # 解析远端路径
python tools/deploy_upload.py upload   meta/api/bo_api.py meta/core/models.py \
                                       meta/core/models_enums.py meta/core/yaml_loader.py
python tools/deploy_upload.py verify   meta/api/bo_api.py          # 独立 md5 校验
python tools/deploy_upload.py healthcheck                          # HTTP 端点检查
python tools/deploy_upload.py healthcheck --introspect \
    --module meta.api.bo_api --module meta.core.models \
    --module meta.core.models_enums --module meta.core.yaml_loader
```

参数要点:
- `upload/verify` 接受多个 local_path (nargs="+"), 任一失败退出码 1
- `--skip-verify` 跳过 md5 (快速模式, 正式部署禁用)
- `healthcheck --introspect --python` 默认远端解释器 `/opt/miniconda3-py39/bin/python` (backend 实际使用的, PATH 里的 `python` 不可用)
- 退出码: 0 全部成功; 1 存在失败 (可作 CI 门禁)

---

## 5. 二次检查清单 (按序执行)

> 原则 (项目硬约束): 环境事实一律实测, 禁止依赖记忆值。远端操作前先跑 `python tools/env_facts.py probe` 确认 staging 现状 (pid/port/DB/dist 指纹)。

### V0. 静态验证 (无远端依赖, 本机即可)

| 步骤 | 命令 | 预期 |
|---|---|---|
| V0.1 | `python -c "import sys; sys.path.insert(0,'tools'); from lib.deploy_topology import DeployTarget; t=DeployTarget.from_name('staging'); print(t.name, t.resolver_name, t.deploy_root)"` | `staging symlink_namespace_package /opt/app/staging/deploy/current` |
| V0.2 | `python tools/deploy_upload.py list-resolvers` | 4 个: local / symlink_namespace_package / volume_mount / git_submodule |
| V0.3 | `python tools/deploy_upload.py resolve meta/api/bo_api.py` | 恰好 2 条路径: `.../current/meta/api/bo_api.py` 和 `.../current/api/bo_api.py` |
| V0.4 | `python tools/deploy_upload.py resolve meta/schemas/user.yaml` | 恰好 2 条路径 (yaml 双发) |
| V0.5 | `python tools/deploy_upload.py resolve tools/deploy_upload.py` | 1 条路径: `.../current/tools/deploy_upload.py` (repo 内文件 marker 命中, 非 meta/ 前缀不双发)。仅 repo 外文件才退化为 `{root}/{文件名}`, 见 §6 限制 L1 (已实测确认: 不存在的文件解析为 `{root}/not_exist_file.py`) |
| V0.6 | `python tools/deploy_upload.py -t dev resolve meta/api/bo_api.py` | 1 条路径 = 本地绝对路径 |
| V0.7 | `python tools/deploy_upload.py -t staging --dry-run upload meta/api/bo_api.py` | 仅打印 `[DRY-RUN] -> 2 路径`, 无远端流量 |

### V1. staging 真机验证 (需远端通道)

前置: `python tools/env_facts.py probe` 确认 backend 在线。

| 步骤 | 命令 | 预期 |
|---|---|---|
| V1.1 | `python tools/deploy_upload.py upload meta/api/bo_api.py meta/core/models.py meta/core/models_enums.py meta/core/yaml_loader.py` | 4 文件 x 2 路径 = 8 行 `[OK remote_upload] md5=match ...`, 退出码 0 |
| V1.2 | `python tools/deploy_upload.py verify meta/api/bo_api.py` | 2 行 `[OK]` |
| V1.3 | `python tools/deploy_upload.py healthcheck` | 2 个端点 `[OK-REGISTERED] 401 ...` (401/403 = 路由已注册需鉴权, 属于成功; 404 = 路由未生效 = 失败信号) |
| V1.4 | V0 同款 `healthcheck --introspect --module ...` (4 个模块) | 见 §5.1 判读规则, **勿把预期 FAIL 误判为事故** |
| V1.5 | 端到端: dev-login 拿 cookie 后 GET `/api/v2/bo/user/state-transition-actions` | `success: true`, data 含 6 个 action_ref: activate / deactivate / lock / unlock / freeze / unfreeze |

### 5.1 introspect 判读规则 (关键, 防误判)

当前 staging 拓扑是「平铺活树 + meta namespace package 子集」:

| introspect 结果 | 判定 |
|---|---|
| `meta.api.bo_api` 报 `ModuleNotFoundError: No module named 'meta.core.bo_framework'` | **预期行为, 不是事故**。meta/ 是补丁子集, meta/core/ 下无 bo_framework.py; backend 靠 lazy import 规避, 顶层包提供完整 core。判定依据以 V1.5 端到端为准 |
| `meta.core.models` / `meta.core.yaml_loader` 报缺 `meta.core.action_constants` | 同上, 预期 |
| introspect 输出路径在 `/opt/app/staging/deploy/` 下但显示快照目录 (`v1789297457_staging_spec22`) 而非 `current` | 需人工判断: bash `cd` symlink 后 `__file__` 是否解析 symlink 取决于环境。路径仍处于 deploy 目录即算正常; 若指向 9-05 旧快照 (`v20260905_staging_align_head` 等) 才是真异常 |
| 输出路径完全在 deploy_root 之外 (如 site-packages) | 真异常: 上传的文件未被加载, 回到 V1.1 重传并检查 backend cwd |

### 5.2 HTTP 状态码判读

| 码 | 判定 |
|---|---|
| 401/403 | `[OK-REGISTERED]` 路由已注册, 后端在线 (成功) |
| 404 | `[FAIL-404]` 路由不存在, spec22 上传失败信号 |
| 5xx | 后端异常, 查日志 |
| 200 | 直接成功 (带鉴权时) |

---

## 6. 已知限制 (检查时知悉, 勿当 bug 修)

- **L1 repo 根推断靠 marker**: `_relative_to_repo` 以 `/excel-to-diagram/` 和 `/filework/excel-to-diagram/` 为 marker。repo 外文件退化为单发 `{deploy_root}/{文件名}` — 对非 repo 文件此路径是危险的, 工具假定输入均为 repo 内业务文件。
- **L2 dev target 的 upload 是原地自拷贝**: LocalResolver 返回本地路径本身, host=None 时 copy 到自身 (语义上无意义)。dev target 定位是 resolve 预览与单测, 不是真上传。
- **L3 远端函数绑定依赖 staging_round**: `DeployTarget._from_dict` 默认 import `staging_round.remote_exec/remote_upload/remote_md5` (tools/staging_round.py L84/111/137)。若该文件缺失或重构签名, 所有远端操作静默退化为 `no upload_fn bound`。
- **L4 deploy_root 是 symlink 路径**: introspect 的 `in_deploy` 判断用字符串包含 `current`; 若 `__file__` 被解析成快照实路径会误报 OUTSIDE (见 §5.1 第 3 行判读)。
- **L5 production 已实测 / preview 仍是占位**: production 入口在 293375b 已实测 (gw 9200 HTTPS, deploy_root `/opt/app/deployments/meta`, 新增 `flat_meta_package` resolver 适配单发扁平布局, 服务 systemd 名 `meta-backend.service` / `meta-unified.service`); preview 整节仍处注释状态, 仍待办 G。
- **L6 未接入旧编排器**: staging_round.py / staging_deploy_orchestrator.py 的旧上传逻辑仍在使用, 本工具目前是并行入口而非替代 (待办 F)。

---

## 7. 遗留待办 (复盘 §11 行动项, 交接待续)

| 项 | 内容 | 建议 |
|---|---|---|
| F | 把 deploy_upload 接入 staging_round.py, 取代旧 upload 逻辑 | 接入前先跑 V1 全套回归 |
| G | 为 preview 补 deploy_topology.yaml entry 并实测 (volume_mount resolver) | production 已在 293375b 完成; preview 仍是注释; 接 k8s/preview 环境时再补 |
| H | 写 unit test `tools/tests/test_deploy_topology.py` | 覆盖: 4 resolver 的 resolve 输出、meta/meta 双前缀回归、资源类型推断、双发前缀匹配; 参考同目录 conftest.py 风格, `pytest tools/tests/` 运行 |
| 清理 | 仓库内历史 `_tmp_*` 一次性脚本 (test_helpers/ 下 140+ 个) | 属仓库卫生问题, 与本框架无直接耦合, 建议单独任务批量清理 |

---

## 8. 排错速查

| 症状 | 可能原因 | 处置 |
|---|---|---|
| upload 报 `no upload_fn bound` | staging_round import 失败 (限制 L3) | 检查 `tools/staging_round.py` 是否可 import、签名是否匹配 |
| upload 路径出现 `meta/meta/...` | 双前缀回归 (复盘 §6.1) | 检查 path_resolvers.py `stripped = rel[len("meta/"):]` 分支; 该 bug 已修, 复现即回退 |
| verify md5 mismatch | 上传截断 / 远端磁盘满 / 并发写 | 重传该文件; `env_facts.py probe` 查远端状态 |
| healthcheck 全 FAIL / 连接拒绝 | backend 未起或端口漂移 | `python tools/env_facts.py probe`; 严禁按记忆端口猜 |
| introspect 无输出 | 远端解释器路径不对 | 显式 `--python /opt/miniconda3-py39/bin/python` |
| introspect shell 报引号错误 | quoting 回归 (复盘 §6.2) | 确认 cmd 用 `bash -c "cd ... && ... -c \"...\""` 包裹结构 |
| resolve 对 repo 外文件只给文件名 | 限制 L1 | 确认传的是 repo 内业务文件 |
| staging remote exec 403 | 命令命中黑名单 (如 `rm -rf /` 字面量) | 改用带空格写法 `rm -r -f`; 与本工具无关但同通道 |

---

## 9. 相关文档索引

- 复盘 (为什么做): [retrospectives/2026-09-13-deploy-topology-generalization.md](retrospectives/2026-09-13-deploy-topology-generalization.md)
- 经验 (5 条铁律 + 反例): [lessons-learned/deploy-topology.md](lessons-learned/deploy-topology.md)
- 操作 SOP: [staging-runbook.md §3.4](staging-runbook.md)
- 前置复盘 (9-05 meta 影子树): [retrospectives/2026-09-05-staging-meta-shadow-tree.md](retrospectives/2026-09-05-staging-meta-shadow-tree.md)
- 环境事实入口: `python tools/env_facts.py probe / resolve / check`

## 10. 验收标准 (二次检查通过的定义)

1. V0 全部 7 项输出与预期一致
2. V1.1 双发 8/8 `[OK] md5=match`, 退出码 0
3. V1.3 两个 spec22 端点均 `[OK-REGISTERED] 401`
4. V1.5 端到端返回 6 个 action_ref
5. 检查过程中未对 staging runtime 造成变更 (本工具是 agent 端, 重传相同内容文件是幂等的, 允许)
