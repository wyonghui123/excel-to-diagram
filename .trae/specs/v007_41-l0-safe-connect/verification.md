# V007.41 验证清单

> **使用方式**：每个 Verification 命令执行后填入结果。V007.41 完成必须全部通过。

## V.1 单元测试

### V.1.1 safe_connect 单元测试

**命令**：
```bash
cd D:\filework\release-prep-worktree
python -m pytest meta/tests/test_v007_41_safe_connect.py -v
```

**预期**：
- 9 个测试用例 100% 通过
- 覆盖：read / write / force_no_tx / UNKNOWN / auto mode / metric / config

**结果**：____

### V.1.2 L0 写事务回滚测试

**命令**：
```bash
python -m pytest meta/tests/test_v007_41_l0_write_in_tx.py -v
```

**预期**：
- 4 个测试用例 100% 通过
- 覆盖：intent_resolver / subflow_template_store / filter_variant_api / 综合 silent partial commit

**结果**：____

### V.1.3 sql_config 测试

**命令**：
```bash
python -m pytest meta/tests/test_sql_config.py -v
```

**预期**：
- SafeConnectConfig 字段断言通过
- 默认值与 V007.40 一致

**结果**：____

## V.2 集成验证

### V.2.1 V007.41 验证脚本

**命令**：
```bash
cd D:\filework\release-prep-worktree
python verify_v007_41.py
```

**预期**（15/15 通过）：
- Test 1: meta/{core,services,api,handlers}/ sqlite3.connect = 0 处
- Test 2: safe_connect.py 存在且导出 3 个公共 API
- Test 3: SafeConnectConfig 默认值正确
- Test 4: observability.OBS_COUNTERS 含 4 个新 metric
- Test 5: intent_resolver 已删 _safe_connect
- Test 6: subflow_template_store 已删 _safe_connect
- Test 7: runtime_dimension_resolver 中 sqlite3.connect = 0
- Test 8: dim_scope_overlap_detector 中 sqlite3.connect = 0
- Test 9: audit_export 中 sqlite3.connect = 0
- Test 10: sql_adapters.fresh_connection 走 safe_connect
- Test 11: app_builder 中 sqlite3.connect = 0
- Test 12: safe_connect_for_write 无事务 raise
- Test 13: safe_connect_for_write(force_no_tx=True) 不 raise
- Test 14: safe_connect_for_read 默认参数与 V007.40 三件套一致
- Test 15: V007.40 verify_v007_40.py 14 项仍 100% 通过

**结果**：____

### V.2.2 V007.40 回归验证

**命令**：
```bash
python verify_v007_40.py
```

**预期**：14/14 仍通过（零破坏性）

**结果**：____

### V.2.3 测试套件整体

**命令**：
```bash
python -m pytest meta/tests/ -v --tb=short 2>&1 | tail -30
```

**预期**：
- 所有现有测试仍通过
- 失败用例 = 0

**结果**：____

## V.3 部署验证

### V.3.1 release-prep 服务器部署

**触发**：devops-deploy-sop skill
**端口**：3006 / 3011

**监控指标**（部署后 24h）：
- [ ] `v007_41_safe_connect_read_total` 持续增长（每分钟数百次）
- [ ] `v007_41_safe_connect_write_total` 持续增长（每分钟数十次）
- [ ] `v007_41_safe_connect_write_no_tx_total` = **0**（如果有 > 0 说明有写路径漏迁，需排查）
- [ ] `v007_41_safe_connect_tx_state_unknown_total` ≈ 0
- [ ] disk I/O error 日志 = **0**
- [ ] database is locked 错误日志 = **0**

**结果**：____

### V.3.2 yonaa 生产部署

**触发**：devops-deploy-sop skill
**端口**：3004 / 3009

**灰度策略**：
- T+0: 部署 1/4 实例
- T+2h: 全量部署（如无异常）

**监控指标**（部署后 1 周）：
- [ ] disk I/O error 日志 = **0**
- [ ] database is locked 错误 = **0**
- [ ] intent_resolver.grant 调用成功率 = 100%
- [ ] filter_variant_api POST/PUT/DELETE 成功率 = 100%
- [ ] `v007_41_safe_connect_write_no_tx_total` = **0**
- [ ] API 平均响应时间 < 200ms（P95 < 500ms）

**结果**：____

## V.4 文档验证

### V.4.1 spec.md 完整性

**文件**：`d:\filework\release-prep-worktree\.trae\specs\v007_41-l0-safe-connect\spec.md`

**检查项**：
- [ ] 包含 10 个章节（Background, Requirements, Module Design, Migration, Risk, etc.）
- [ ] FR-001 ~ FR-008 全部定义
- [ ] NFR-001 ~ NFR-004 全部定义
- [ ] Module Design 含 safe_connect.py 骨架

### V.4.2 docs/SPEC_V007.41.md 镜像

**文件**：`d:\filework\release-prep-worktree\docs\SPEC_V007.41.md`

**检查项**：
- [ ] 文件存在
- [ ] 与 spec.md 内容一致

### V.4.3 checklist.md 完整性

**文件**：`d:\filework\release-prep-worktree\.trae\specs\v007_41-l0-safe-connect\checklist.md`

**检查项**：
- [ ] Phase 1-4 任务清单完整
- [ ] 验证阶段 V.1-V.4 完整

### V.4.4 tasks.md 完整性

**文件**：`d:\filework\release-prep-worktree\.trae\specs\v007_41-l0-safe-connect\tasks.md`

**检查项**：
- [ ] 11 个 Task 全部定义
- [ ] 每个 Task 子任务明确
- [ ] 提交规范清晰

### V.4.5 implementation_plan.md 完整性

**文件**：`d:\filework\release-prep-worktree\.trae\specs\v007_41-l0-safe-connect\implementation_plan.md`

**检查项**：
- [ ] 4 个 Phase 时间表
- [ ] 回滚策略明确
- [ ] 关键代码变更预览

### V.4.6 .trae/rules/core/checklist.md 更新

**文件**：`d:\filework\release-prep-worktree\.trae\rules\core\checklist.md`

**检查项**：
- [ ] 加 V007.41 检查项（L0 工厂、tx_state 守卫、写迁移）
- [ ] 引用 `meta/core/safe_connect.py`

## V.5 架构验证

### V.5.1 唯一性

**命令**：
```bash
cd D:\filework\release-prep-worktree
grep -rn "sqlite3\.connect(" meta/core meta/services meta/api meta/handlers \
  --include="*.py" 2>/dev/null
```

**预期**：0 行输出（仅 `meta/core/safe_connect.py` 内部允许）

**结果**：____

### V.5.2 本地 helper 删除

**命令**：
```bash
grep -rn "_safe_connect\|def _get_connection" meta/ --include="*.py" 2>/dev/null
```

**预期**：0 行输出（除 safe_connect.py 内部 + 测试代码）

**结果**：____

### V.5.3 V007.40 "三件套"残留

**命令**：
```bash
grep -rn "timeout=30\.0\|busy_timeout = 30000\|check_same_thread=False" \
  meta/core meta/services meta/api meta/handlers --include="*.py" 2>/dev/null
```

**预期**：仅 `meta/core/safe_connect.py` 内部 + `meta/core/sql_connection_pool.py`（pool 路径不动）

**结果**：____

### V.5.4 写迁移验证

**命令**：
```bash
grep -rn "bo_framework.transaction" meta/api meta/handlers --include="*.py" 2>/dev/null
```

**预期**：4 处业务调用方已加 `with bo_framework.transaction() as txn:` 包裹

**结果**：____

## V.6 验收总结

**V007.41 完成判定**：

| 阶段 | 必须 | 实际 |
|---|---|---|
| V.1 单元测试 | 100% 通过 | ____ |
| V.2 集成验证 | 15/15 + 14/14 通过 | ____ |
| V.3 部署验证 | 24h 无 disk I/O error | ____ |
| V.4 文档验证 | 6 项全部勾选 | ____ |
| V.5 架构验证 | 4 项全部 0 处或匹配 | ____ |

**判定**：
- [ ] V007.41 完成
- [ ] V007.41 未完成（需补充项：____）