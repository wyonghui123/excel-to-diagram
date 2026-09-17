# HANDOFF: staging meta 影子树 — 全量对齐 main HEAD + 死镜像清理

> 交接日期: 2026-09-05 | 交接方: 开发智能体（根因分析完成） | 接收方: 部署智能体
> 状态: 用户已拍板 **采纳推荐方案（A + B）**，待执行
> 详细根因分析: [docs/retrospectives/2026-09-05-staging-meta-shadow-tree.md](./retrospectives/2026-09-05-staging-meta-shadow-tree.md)

---

## 1. 一句话任务

将 staging 后端 live 活树（基线 commit 15654ec + 7 个文件级热修）**全量对齐 main HEAD**，
并清理 `current/meta/**` 死镜像，全程用 import origin 门禁 + 行为级送达验证把关。

## 2. 必读：staging 运行时真相（动手前必须理解）

```
server.py L16: sys.path.insert(0, '/opt/app/staging/deploy')
/opt/app/staging/deploy/meta -> symlink -> /opt/app/staging/deploy/current

⇒ import meta           → deploy/meta → current/ 根目录本身（meta 包 = current 根）
⇒ meta.services.X       → current/services/X.py      ← 唯一活树
⇒ current/meta/**       → 永不解析（死镜像，从未被任何进程加载）
```

- repo 路径 `meta/<X>/<file>.py` 的部署目标恒为 `current/<X>/<file>.py`（**去掉 meta/ 前缀，平铺**）。
- 布局来历: `deploy_staging.sh` L29 `cp -r $PROD_DIR/meta/* $NEW_DIR/` —— 版本目录 = meta 包内容平铺。
- 死镜像来历: 9-03 一次"按仓库原样打包"的全量推送，此后 9-04 多个文件也误入死路径。

## 3. 当前双树状态（2026-09-05 md5 实测）

| 树 | 代码基线 | 缺失的关键修复 |
|---|---|---|
| live 活树 `current/<api,services,core,...>` | commit **15654ec** + 热修: permission_config_loader.py、permission_dimension_engine.py(9-01)、manage_api.py(9-02)、org_service.py(9-05) | 449aa1c 的 dimension_scope POST 归一、48ca72a 的 db_path 统一解析、8-30 之后其余 commit |
| 死镜像 `current/meta/**` | main HEAD 快照（9-03 打入） | 内容最新但从未运行 |

风险缺口（对齐后将一并消除）:
1. `permission_set_dimension_scope_api.py` POST 归一（ID-form）不在 live → staging 仍可能写回 OBJ-form（目前靠 GET 旧代码 + v083 数据清洗掩盖）。
2. `core/db_path.py`（48ca72a）在 live 不存在 → DB 路径解析靠 server env `SQLITE_DB_PATH` 兜底。

## 4. 执行方案（用户已批准）

### Phase 0 — 准备与前置检查
1. 确认 main HEAD 干净可用：`git log --oneline -1`，本次对齐目标 = main HEAD（83eb505 及之前全部后端 commit）。
2. **注意**: 不能直接跑 `deploy_staging.sh`（它从 prod 的 `$PROD_DIR/meta` 拷贝，prod meta 是否= main HEAD 未审计）。必须**从 repo main HEAD 打包 `meta/*` 平铺上传**。
3. 上传 `tools/check_meta_import_origin.py` 到远端 `/tmp/`（后续门禁用）。

### Phase 1 — 打包与门禁预检
4. 本地打包: zip 仓库 `meta/` **内容**（解压后根目录直接是 api/ services/ core/ ...，不含 meta/ 前缀层），Python zipfile 打包（禁 Compress-Archive，路径分隔符问题）。
5. 上传到远端精确路径（如 `/tmp/deploy_bundle/`，路径必须精确，勿用模糊表述）。
6. 远端解压到新版本目录: `NEW_VER=v$(date +%Y%m%d_%H%M%S)_staging_align_head`；`mkdir /opt/app/staging/deploy/$NEW_VER && unzip → $NEW_VER/`。
7. 对抽样关键文件跑门禁: `python -I /tmp/check_meta_import_origin.py <rel>`（如 `meta/services/permission_set_dimension_scope_api.py`），断言 LIVE 落点正确。

### Phase 2 — 切换与死镜像清理（同批）
8. `ln -sfn $NEW_VER /opt/app/staging/deploy/current`（原子切换）。
9. **清理死镜像**（在版本目录内，勿动 deploy/meta 符号链接！）:
   `mv /opt/app/staging/deploy/$NEW_VER/meta /opt/app/staging/deploy/$NEW_VER/.dead_meta_bak_$(date +%Y%m%d_%H%M%S)`
   > ⚠️ 绝对禁止 `mv /opt/app/staging/deploy/meta`（那是 import 解析锚点符号链接）。
10. 重启 staging 后端: `bash /opt/app/staging/scripts/start_staging.sh`（或 staging_services.sh），确认新 PID；用 `/proc/<pid>/environ` 含 `PORT=13011` 识别 meta_backend。

### Phase 3 — 送达验证（md5/py_compile/dev-login 均不算送达证明）
| # | 验证项 | 通过标准 | 对应修复 |
|---|---|---|---|
| 1 | 真实登录 | 200 OK（非 dev-login 形式化） | 基线 |
| 2 | 组织详情「资源 × 功能权限」矩阵 | 3 个权限集（财资管理子领域编辑/大财务架构数据查看/YonBIP产品查看）及条件行"查看（1 条）"正常显示 | 83eb505 + a04d2ee |
| 3 | dimension-scope **写入后读回** | POST 权限集维度范围 → GET 返回 ID-form（`[13]` / `['*']`），不出现 OBJ-form `[object Object]` | 449aa1c（本次对齐的核心收益） |
| 4 | DB 路径 | 服务启动正常、业务表可读写（db_path.py 送达后仍受 env `SQLITE_DB_PATH` 兜底，行为应无回归） | 48ca72a |
| 5 | smoke test | `staging_e2e_test.sh` 全过 | 基线 |
| 6 | 浏览器级验证 | 172.20.59.7:18081 UI 实际数据路径验证（权限矩阵、导出） | 基线 |

### Phase 4 — 回滚预案（版本目录机制天然支持）
- 旧版本目录保留不动。任一验证失败:
  `ln -sfn <旧版本目录名> /opt/app/staging/deploy/current && bash start_staging.sh`
- 回滚后死镜像 bak 目录保留（不影响运行，仅供审计）。

## 5. 硬约束（违反即事故重演）

1. **禁止向 `current/meta/**` 部署任何文件**；禁止"两份都写"保持一致。
2. 任何 meta/** 文件部署前必须 `python -I` 跑 `check_meta_import_origin.py` 断言 LIVE 落点（EXIT 1 即中止）。
3. 远端 python 脚本一律 `python -I`（/tmp 曾出现 inspect.py 标准库遮蔽，已隔离为 inspect.py.quarantined_20260905）。
4. 打包必须平铺（meta/* 内容在压缩包根），严禁仓库原样结构（那正是死镜像的成因）。
5. 部署后必须有**运行中进程可见的行为差异**作为送达证明；插桩/探针日志在正确文件里为空 = 未加载的第一信号。
6. 复刻 sys.path 实验时严格按 `[deploy, current]` 顺序（顺序反了结论相反，已真实踩坑）。
7. gateway 命令白名单有限（禁 rm/变量），变通时勿引入 /tmp 污染。
8. 本次仅后端 meta 包；前端 dist 链路不在范围。

## 6. 仓库侧待办（部署智能体不处理，仅告知）

- 复盘文档 `docs/retrospectives/2026-09-05-staging-meta-shadow-tree.md` 与本交接文档尚未 commit。
- 门禁工具 `tools/check_meta_import_origin.py` 已入库。

## 7. 参考资料

- 根因复盘: docs/retrospectives/2026-09-05-staging-meta-shadow-tree.md
- 门禁工具: tools/check_meta_import_origin.py（必须 `python -I` 运行）
- 现行部署脚本（仅参考布局来历，勿直接用于本次对齐）: tools/deploy_staging.sh
- 相关 commit: 83eb505（org_service 权限预览）、449aa1c（dimension-scopes 归一）、48ca72a（db_path）、a04d2ee（row_scope 收紧）、fc7c364（预览500修复）
