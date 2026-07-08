# V007.41 实施检查清单

> **使用方式**：每完成一项打勾并写明 commit hash。所有项完成后即可进入验证阶段。

## Phase 1: 工厂实现

- [ ] **1.1** 新增 `meta/core/safe_connect.py`（FR-001 核心代码）
  - `safe_connect_for_read(db_path)` 函数
  - `safe_connect_for_write(db_path, force_no_tx=False)` 函数
  - `safe_connect(db_path, mode="auto")` 兼容函数
  - 公共 contextmanager 风格
  - commit: ____

- [ ] **1.2** 新增 `SafeConnectConfig` 到 `meta/core/sql_config.py`（FR-007）
  - 字段：`timeout / busy_timeout_ms / check_same_thread / enforce_write_in_tx / tx_state_unknown_passthrough`
  - 默认值与 V007.40 一致（timeout=30.0, busy_timeout=30000）
  - `get_safe_connect_config()` 函数
  - commit: ____

- [ ] **1.3** 新增 4 个 metric 到 `meta/core/observability.py`（FR-006）
  - `v007_41_safe_connect_read_total`
  - `v007_41_safe_connect_write_total`
  - `v007_41_safe_connect_write_no_tx_total`
  - `v007_41_safe_connect_tx_state_unknown_total`
  - commit: ____

- [ ] **1.4** 新增 `meta/tests/test_v007_41_safe_connect.py`
  - 测试 `safe_connect_for_read` 默认参数
  - 测试 `safe_connect_for_write` 强制事务（raise）
  - 测试 `force_no_tx=True` 绕过
  - 测试 `tx_state=UNKNOWN` 降级
  - 测试 metric 计数
  - 100% 通过
  - commit: ____

## Phase 2: 现有 17 处迁移

- [ ] **2.1** 迁移 4 个本地 helper 持有者
  - `intent_resolver._safe_connect` → 删，改 `safe_connect_for_read`
  - `subflow_template_store._safe_connect` → 删，改 `safe_connect_for_read`
  - `token_blacklist_service._get_connection` → 删，改 `safe_connect_for_read`
  - `filter_variant_api._execute_query` → 拆分 read / write
  - commit: ____

- [ ] **2.2** 迁移 13 个内联 sqlite3.connect
  - `runtime_dimension_resolver.py` 3 处（`_try_resolve_upward` / `_get_user_roles` / `_get_role_dim_scopes`）
  - `dim_scope_overlap_detector.py` 2 处（`_get_dim_scopes` / `_get_condition_rules`）
  - `audit_export.py` 1 处
  - `sql_adapters.fresh_connection()` 1 处
  - `app_builder.py` 2 处（preflight + startup）
  - commit: ____

- [ ] **2.3** V007.40 加的"三件套"代码整段删除
  - `git diff` 确认 `timeout=30.0` / `PRAGMA busy_timeout = 30000` / `check_same_thread=False` 在生产代码中删除（被 safe_connect 接管）
  - 例外：`migrations/ scripts/ tests/conftest.py` 不动
  - commit: ____

## Phase 3: 写迁移到 V3

- [ ] **3.1** 列出 `intent_resolver.grant/deny/revoke` 所有调用方
  - grep 结果: ____

- [ ] **3.2** 调用方加 `bo_framework.transaction()` 包裹
  - intent_resolver 调用方全部加 `with bo_framework.transaction() as txn:`
  - commit: ____

- [ ] **3.3** `intent_resolver` 内部 `sqlite3.connect` → `safe_connect_for_write`
  - commit: ____

- [ ] **3.4** `subflow_template_store.delete/save` 同上迁移
  - commit: ____

- [ ] **3.5** `filter_variant_api` 拆分 `_execute_query` 为 read / write 两个版本
  - `_execute_read_query(sql, params)` → `safe_connect_for_read`
  - `_execute_write_query(sql, params)` → `safe_connect_for_write`
  - 调用方 POST/PUT/DELETE 路由包 `bo_framework.transaction()`
  - commit: ____

- [ ] **3.6** `token_blacklist_service._cleanup_expired` 决策
  - 决策: ____
  - 选项 A: 保留 L0 + `force_no_tx=True`（cleanup 独立事务）
  - 选项 B: 迁移到 `bo_framework.transaction()`（每次请求多一层事务）
  - commit: ____

- [ ] **3.7** 新增 `meta/tests/test_v007_41_l0_write_in_tx.py`
  - 测试 `intent_resolver.grant` 在外层事务失败时确实回滚（不能 silent partial commit）
  - 测试 `subflow_template_store.delete` 同上
  - 测试 `filter_variant_api.create_variant` 同上
  - 100% 通过
  - commit: ____

## Phase 4: 唯一性检查 + 文档

- [ ] **4.1** 新增 `verify_v007_41.py`
  - Test 1: `meta/{core,services,api,handlers}/` 中 `sqlite3\.connect\(` 数量 = 0
  - Test 2: `meta/core/safe_connect.py` 存在且导出 3 个公共 API
  - Test 3: `sql_config.SafeConnectConfig` 默认值与 V007.40 一致
  - Test 4: `observability.OBS_COUNTERS` 含 4 个新 metric
  - Test 5: `intent_resolver` 已删除 `_safe_connect` 本地 helper
  - Test 6: `subflow_template_store` 已删除 `_safe_connect` 本地 helper
  - Test 7: `runtime_dimension_resolver` 中 `sqlite3.connect` = 0 处
  - Test 8: `dim_scope_overlap_detector` 中 `sqlite3.connect` = 0 处
  - Test 9: `audit_export` 中 `sqlite3.connect` = 0 处
  - Test 10: `sql_adapters.fresh_connection` 走 safe_connect
  - Test 11: `app_builder` 中 `sqlite3.connect` = 0 处
  - Test 12: `safe_connect_for_write` 无事务时 raise
  - Test 13: `safe_connect_for_write(force_no_tx=True)` 不 raise
  - Test 14: `safe_connect_for_read` 默认参数与 V007.40 三件套一致
  - Test 15: V007.40 verify_v007_40.py 14 项仍 100% 通过
  - 100% 通过
  - commit: ____

- [ ] **4.2** 复制本 spec 到 `docs/SPEC_V007.41.md`
  - commit: ____

- [ ] **4.3** 更新 `.trae/rules/core/checklist.md`
  - 加 V007.41 检查项：L0 直连工厂、tx_state 守卫、写迁移
  - commit: ____

## 验证阶段

- [ ] **V.1** 单元测试 100% 通过
  - `pytest meta/tests/test_v007_41_safe_connect.py`
  - `pytest meta/tests/test_v007_41_l0_write_in_tx.py`
  - 结果: ____

- [ ] **V.2** 集成验证 100% 通过
  - `python verify_v007_41.py`
  - `python verify_v007_40.py` (回归)
  - 结果: ____

- [ ] **V.3** 部署到 release-prep 服务器
  - 通过 devops-deploy-sop skill
  - 监控 24h disk I/O error = 0 复发
  - 结果: ____

- [ ] **V.4** 部署到 yonaa 生产
  - 灰度 1 个实例 → 全量
  - 监控 1 周 disk I/O error = 0 复发
  - 结果: ____

## 提交规范

每个 Phase 单独 commit，commit message 格式：

```
fix(be): V007.41 P<n> - <Phase 简称>

<详情>
```

例如：
```
fix(be): V007.41 P1 - safe_connect factory + SafeConnectConfig + metric

[V007.41] Phase 1 工厂实现
- meta/core/safe_connect.py: 统一 L0 工厂
- meta/core/sql_config.py: SafeConnectConfig
- meta/core/observability.py: 4 个新 metric
- meta/tests/test_v007_41_safe_connect.py: 单元测试
```