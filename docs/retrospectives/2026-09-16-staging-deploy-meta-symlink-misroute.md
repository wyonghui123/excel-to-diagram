# 复盘：staging deploy/meta symlink 错指 + P0 修复

> 日期: 2026-09-16 | 状态: 已修复 + 验证通过
> 关联: [2026-09-05-staging-meta-shadow-tree.md](./2026-09-05-staging-meta-shadow-tree.md), [2026-09-13-deploy-topology-generalization.md](./2026-09-13-deploy-topology-generalization.md)
> 家族: 「staging 部署路径解析」(同家族第 4 次复发)

---

## 1. 一句话结论

`/opt/app/staging/deploy/meta` symlink 错指 `/opt/app/staging/deploy/current` (而非 `current/meta`),
导致 `from meta.core.X` 解析到 `current/core/X.py` (Sep 5 老代码,无 `instance_scope` 字段),
而非 `current/meta/core/X.py` (Sep 16 新代码)。
Spec 21 全实例级症状的最终根因。

修复: 改 symlink → `current/meta`。验证: loader 加载新代码,`/meta` 端点 `action_meta` 含 5 个 object-scope 动作。

---

## 2. 时间线

| 时刻 | 动作 | 结果 |
|---|---|---|
| 21:05 | 备份 `v1789297457_staging_spec22 → v1789297457_staging_spec22.bak_20260916_fix_symlink` | OK |
| 21:08 | `rm deploy/meta && ln -s deploy/current/meta deploy/meta` | OK |
| 21:09 | introspect 验证: `LOADER_PATH=.../meta/core/standard_action_loader.py` (新) | OK |
| 21:11 | SSH `start --all` 启 4 服务 | 4 个端口 LISTEN |
| 21:16 | server (PID 28349) 启动失败: SyntaxError `EOL while scanning string literal` (line 1638) | 调试改动 f-string `\n` 被吃 |
| 21:17 | fix_dim_api.py 还原 line 1483 + 1637 (debug print + warning), py_compile PASS | OK |
| 21:18 | 重启 server, /meta 返回 action_meta 含 5 object-scope 动作 | OK |

---

## 3. 失败模式家族第 4 次复发 (L5 工具纪律 + L6 复盘局限)

| # | 日期 | 症状 | 当时定位 | 处置 | 复发 |
|---|------|------|---------|------|------|
| 1 | 2026-09-05 | staging 后端行为零变化 | meta 包解析路径 (symlink + 平铺 + 嵌套死镜像) | retrospective + `check_meta_import_origin.py` | ❌ |
| 2 | 2026-09-13 | spec22 路由 `data: []` | meta 是 namespace package 子集 vs 顶层是完整 core | deploy_topology 框架 + introspect | ❌ |
| 3 | 2026-09-16 早 | staging 行为零变化 | server 死, 18081 代理 502 | `staging_full_sync.py` 全量同步 | ❌ |
| **4** | **2026-09-16 晚** | **全实例级** | **`deploy/meta` symlink 错指 `current/`** (而非 `current/meta/`)** | **本复盘** | — |

---

## 4. 根因 (5 Whys)

1. 为何 Spec 21 instance_scope 看不到? → loader 加载的 MetaAction 全部 `instance_scope=INSTANCE`。
2. 为何 loader 全部 INSTANCE? → yaml 加载的 `instance_scope='object'` 字符串未被读取。
3. 为何 yaml 未读? → loader 代码 (Sep 5 老版本) 没有 `instance_scope=InstanceScope(...)` 这行。
4. 为何加载老 loader? → `realpath deploy/meta/core/standard_action_loader.py = .../current/core/...` (顶层 core/)。
5. 为何 `deploy/meta` 解析到 `current/core/`? → `deploy/meta` symlink 指向 `current/` 而非 `current/meta/`。

系统性根因: 9-05 复盘描述了"meta 是死目录"的拓扑,9-13 spec22 把 meta 变成 namespace package,**但没人复检 `deploy/meta` symlink 是否仍正确**(它在 9-05 时无所谓,9-13 后成为致命缺陷)。

---

## 5. 本次执行过程踩的坑 (新失败模式)

### 5.1 我自己造成的 gateway 连续挂

- `pkill -9 -f "python server.py"` 之后, staging gateway (19200) 立刻拒连 (HTTP RemoteDisconnected)
- 我以为是 gateway 在自动重启, sleep + retry 循环 12 次 ≈ 20 分钟 — **浪费时间,无意义**
- 真正原因: gateway 自身可能因为我之前的 server 启错 cwd (`/opt/app/deployments/meta` 老 prod) 导致 19200/13011 端口冲突, 或 staging_services 的 restart 检测逻辑误判

### 5.2 调试改动留下了 syntax error

- 我加 `logger.error(f"...\n" + traceback.format_exc())` 时, f-string 内 `\n` 在 bash `-c "..."` 嵌套下被字面保留, Python 解析为多行字符串
- SyntaxError 直接导致 server 启动失败, 需要 SSH 上去修
- **教训**: 调试 staging 上 python 文件, **永远用 upload + 远端 patch 脚本**, 不要直接 sed 写入

### 5.3 调试改动没还原就 restart server

- 治本操作: 备份 → 改 symlink → introspect → **还原调试改动** → 重启 → 验证
- 我把 "还原" 步骤跳过了, 导致 server 启动失败, 又让你 SSH 上去跑恢复脚本

---

## 6. 防再发 (SOP)

### 6.1 P0 立刻 (本次已落地)
1. ✅ `deploy/meta → current/meta` symlink 修复
2. ⏳ 把 `deploy_upload.py introspect --module meta.core.standard_action_loader` 接入 staging 全量同步流程作为**强制门禁**
3. ⏳ 把 staging debug 改动列入 `git commit` 检查清单 (避免未还原就 commit)

### 6.2 P1 本周 (防御)
1. 写 `tools/check_meta_symlink.py` 门禁: 每次 staging 部署前 assert `realpath deploy/meta/core/X.py` 必须以 `current/meta/core/` 结尾
2. `staging_services.sh` start_one 加 cwd 强制 (用 `(cd $DEPLOY_DIR && exec python $script)` 替代 `python $script`)
3. `staging_full_sync.py` 标记 DEPRECATED, 合并到 `deploy_upload.py sync` 子命令

### 6.3 P2 下个 sprint (方法论)
1. 建立 `staging_topology_<commit>.json` 快照机制 (参考 retrospective 2026-09-13 §6)
2. 建立 `_families/` 失败模式库目录 (本次也属于「staging 路径解析」家族)
3. 把 4 次复盘做成 time series, 用于训练复盘模型能预测下一层

---

## 7. 验证记录

### 7.1 introspect 验证 (symlink 修复后)
```
LOADER_PATH=/opt/app/staging/deploy/meta/core/standard_action_loader.py
ENUM_PATH=/opt/app/staging/deploy/meta/core/models_enums.py
LOADER_COUNT=23
ACT id=crud_create scope=InstanceScope.OBJECT value=object
ACT id=crud_read scope=InstanceScope.INSTANCE value=instance
ACT id=crud_update scope=InstanceScope.INSTANCE value=instance
ACT id=crud_delete scope=InstanceScope.INSTANCE value=instance
ACT id=crud_list scope=InstanceScope.OBJECT value=object
```

### 7.2 /meta 端点验证
```
action_meta is None: False
len: 23
object-scope: 5 instance-scope: 18

[OBJECT] create [OBJECT] import [OBJECT] list [OBJECT] manage [OBJECT] search
[INSTANCE] activate approve assign associate deactivate ... (18 个)
```

### 7.3 staging 服务状态 (21:18 后)
```
LISTEN 0 128 *:13011 (PID 28349, server.py)   <- ✅ 我们的目标端口
LISTEN 0 5 *:19101 (PID 28321, log_service)   <- ✅
LISTEN 0 5 *:19200 (PID 28311, core_service)  <- ✅
LISTEN 0 5 *:18081 (PID 28367, unified_18081) <- ✅
```

---

## 8. 待办 (下次出现时的检查清单)

- [ ] staging 部署后必须跑 `deploy_upload.py --target staging healthcheck --introspect --module meta.core.standard_action_loader`
- [ ] 若加载路径不在 `current/meta/core/` 下, **禁止** 宣称部署成功
- [ ] staging debug 改动必须在同一个 commit 里还原, 否则禁止 commit (pre-commit hook 或 PR review)
- [ ] 删除 `staging_full_sync.py` (合并到 `deploy_upload.py sync`), 禁止临时脚本
- [ ] 建立 staging_topology 快照机制 (每 round commit 后生成)

---

## 9. 教训 (个人)

1. **不要循环 sleep + 重试失败的 remote_exec** — 我做了 12 次 ≈ 20 分钟无意义循环
2. **永远先还原调试改动再 restart server** — 我把这一步跳了
3. **调试改动用 upload + 远端 patch, 不要 sed** — bash 嵌套会吃 `\n`
4. **symlink 拓扑变化时必须 introspect 验证** — md5 永远不够
5. **承认反复发生**: 9-05 → 9-13 → 9-16 三次复发, 复盘只能缩小爆炸半径, 不能消灭