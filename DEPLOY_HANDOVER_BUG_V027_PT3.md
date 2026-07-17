# DEPLOY HANDOVER: BUG-V027-pt3 — Tuple import 缺失 (本地假成功)

## 📌 任务概述

**用户问题**（PM 通过生产 5001 反馈，2026-07-08 17:48 重新部署后）：

- 用户重新部署 v20260708_010 后测试 export，**结果仍错**：
  - domain 11 / sub_domain 68 / service_module 409 / business_object 3228
- v027-pt2 fix 部署了但**没生效**！

## 🔍 根因 (NEW)

**生产环境 v20260708_010 backend 日志 12 处报错**：

```
[DataPerm] Failed to apply data permission: name 'Tuple' is not defined
```

**BUG 位置**：`meta/services/query_service.py` 顶部 `from typing import`

**当前**：
```python
from typing import List, Dict, Any, Optional
#                              ^^^^^^^^ 没 Tuple
```

**问题**：
- query_service.py:1692-1720 内联函数用了 `Tuple` 类型注解：
  - `def _cond_to_tuple(c: Dict) -> Optional[Tuple[str, _QOp, Any]]:`
  - `def _tup_to_sql(tup: Tuple) -> Tuple[str, list]:`
- 文件顶部 import **没 `Tuple`**

**为什么本地 3018 通过、生产失败**：

| 环境 | Python 版本 | 类型注解行为 | 结果 |
|------|------------|-------------|------|
| 本地 3018 (集成) | 3.14 | **lazy 求值** (PEP 649) | 不报 NameError |
| 生产 5001 | 3.9 (`/opt/miniconda3-py39`) | **立即求值** | **NameError** |

**生产实际行为链**：
1. server.py 启动 → import query_service → 加载 inline 注解 → NameError (lazy 函数不执行)
2. 用户 export 触发 `QueryService.search` → 调 `_apply_data_permission` → 调 `_try_apply_dimension_scope`
3. `_try_apply_dimension_scope` 走完 conds 派生 → 调 `where_raw`
4. `where_raw` 触发 inline 函数 `_cond_to_tuple` / `_tup_to_sql` 注解求值 → **NameError: Tuple not defined**
5. 异常被 `_apply_data_permission` 的 try/except 捕获 → `[DataPerm] Failed to apply data permission`
6. 走 allowed_ids fallback → 全表 → 11/68/409/3228

## ✅ 修复

**Commit**: `76f7668` (worktrees/release-prep HEAD), `b46fe80` (worktrees/integration)

**Fix 内容** (1 行改动)：

```python
# meta/services/query_service.py:1
- from typing import List, Dict, Any, Optional
+ from typing import List, Dict, Any, Optional, Tuple
```

**影响文件**：
- `meta/services/query_service.py` (root)
- `deploy_bundle/meta/services/query_service.py` (部署用)

## 📋 部署要求

**目标环境**：生产 5001 (`172.20.59.7`)

**当前部署**：v20260708_010 (基于 git HEAD `c418d691`，含 v027-pt2 fix 但**缺 Tuple import**)
**目标部署**：v20260708_011 (基于 worktrees/release-prep HEAD `76f7668`)

**部署步骤**：

1. **构建新 zip**（在 worktrees/release-prep）
   ```bash
   cd D:\filework\worktrees/release-prep
   python tools/rebuild_zip.py
   # 生成 deploy-v20260708_011.zip (HEAD=76f7668)
   ```

2. **传输到生产** (任一方式)
   ```bash
   scp deploy-v20260708_011.zip root@172.20.59.7:/tmp/
   ```

3. **解压并切换**
   ```bash
   # 在生产 /opt/app/deployments/
   mv v20260708_010 v20260708_010.bak
   unzip /tmp/deploy-v20260708_011.zip
   mv <解压目录> v20260708_011

   # 切换 current 软链接
   ln -sfn /opt/app/deployments/v20260708_011 /opt/app/current
   ```

4. **重启后端** (注意 cwd!)
   ```bash
   # 重要: server.py 从 /opt/app/deployments/meta 启动
   # PID file 写入 /opt/app/deployments/meta/server.pid
   # 实际查询服务从 /opt/app/deployments/meta/services/query_service.py 加载
   
   kill 8136  # kill 当前 server.py
   cd /opt/app/deployments/meta
   nohup python server.py > /tmp/server.log 2>&1 &
   
   # 验证启动
   curl http://172.20.59.7:5001/api/v1/health
   ```

5. **验证导出** (用 wyonghui)
   ```bash
   # 检查后端日志不再有 Tuple NameError
   curl http://172.20.59.7:9101/api/log?file=/opt/app/shared/logs/backend-v20260708_011.log&grep=Tuple
   # 应当 0 行匹配
   ```

6. **用户验收**
   - 用 wyonghui 登录
   - 导出 cascade
   - 检查：domain=1~2, sub_domain=5~9, service=21~32, BO=155, 备注=706

## 🧪 验证脚本

**本地 3018 重启验证** (已通过)：
```bash
cd D:\filework\worktrees/integration\meta
python tests\test_export_cascade_v027pt2.py
```

**生产导出验证** (部署后)：
```bash
python probe_prod_export.py
# 期望 total_rows ≈ 900-1059, BO=155, annotation=706
```

## 🔄 Rollback

```bash
ln -sfn /opt/app/deployments/v20260708_010.bak /opt/app/current
kill <new PID>
cd /opt/app/deployments/meta
nohup python server.py > /tmp/server.log 2>&1 &
```

## ⚠️ 关键提醒

**生产环境是 Python 3.9**！本地 3018 用的是 Python 3.14，类型注解行为不一致。

**今后所有内联函数类型注解必须确认 import 完整**：
- `Optional[X]` → X 必须在 typing import
- `Tuple[X, Y]` → 必须 import Tuple
- `Union[X, Y]` → 必须 import Union
- `Callable[[X], Y]` → 必须 import Callable

或：在文件顶部加 `from __future__ import annotations` 让所有注解变 lazy。

## 📁 涉及文件

| 文件 | 改动 | 行 |
|------|------|-----|
| `meta/services/query_service.py` | +1 (Tuple import) | 1 |
| `deploy_bundle/meta/services/query_service.py` | +1 (Tuple import) | 1 |

## 📚 相关文档

- `DEPLOY_HANDOVER_BUG_V027.md` — Phase 1 (bb53b0a)
- `DEPLOY_HANDOVER_BUG_V027_PT2.md` — Phase 2 (单 role AND-merge)
- `DEPLOY_HANDOVER_BUG_V027_PT3.md` — **本文件** (Tuple import)

## ✅ 已完成

- [x] 修复代码已 commit 到 worktrees/release-prep (76f7668)
- [x] 修复代码已 commit 到 worktrees/integration (b46fe80)
- [ ] 重新构建 zip v20260708_011
- [ ] 部署到生产 172.20.59.7
- [ ] 重启生产 5001
- [ ] 用 wyonghui 验证导出 (BO=155)
- [ ] 通知 PM 验收

---

**部署负责人**: 部署智能体
**修复开发者**: AI Assistant (session)
**发现时间**: 2026-07-08 17:55
**目标完成**: 部署完成后 PM 可在生产系统验证导出
