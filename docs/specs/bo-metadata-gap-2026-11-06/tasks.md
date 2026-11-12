# Tasks：BO 元数据缺口补充（2026-11-06）

> 对应 `spec.md`（同目录）。**全部任务需用户批准 D1-D5 后执行**；未批准前只读。
> 测试唯一入口：`python d:\filework\test.py --file <相对路径>`（禁止 pytest）。
> 禁止修改主仓其他会话的未提交改动（v200/v224 迁移、inventory_posting_service、p7/p8 文档）。

---

## 阶段 0：批准与试点选择（无代码）

- [x] **T0 批准 D1-D5** —— 按 spec §9 建议默认批准（D1 试点 purchase_order / D2 type_spec 渐进 / D3 item 试点延后 / D4 保持两套并行 / D5 只定策略清单）—— 验收：5 条决策均有明确选项 —— 依赖：无 —— 优先级 P0
- [x] **T0.1 试点对象确认** —— 默认 `purchase_order`（字段多、状态完整、已有 guard）—— 实际试点 5 个状态：draft / submitted / confirmed / closed / cancelled —— 依赖：T0 —— 优先级 P0

## 阶段 1：S1 状态目录 + 状态 × 字段矩阵（P0）

- [x] **T1.1 元模型增量** ✅ 2026-11-06
  - 文件：`meta/core/models.py`
  - 内容：新增 `MetaStateDefinition`（code/label/category/is_system_locked/seq）、`MetaStateFieldPolicy`（readonly/required/hidden）；`MetaObject` 增加 `states`、`state_field_policies`（默认空）
  - 验收：导入与存量对象构造均正常（默认空 = 完全向后兼容）
  - 依赖：T0.1 —— 规模：S

- [x] **T1.2 YAML 解析 + fail-fast 校验** ✅ 2026-11-06
  - 文件：`meta/core/yaml_loader.py`（`parse_meta_object` 内解析 + 新增 `_validate_state_declarations`）
  - 内容：解析 `states:` / `state_field_policies:`；校验 state 必须在 states 或 transition 的 from/to 中、字段必须在 fields 中，否则启动失败（`ValueError`，`[S1]` 前缀）
  - 验收：`test_state_field_matrix.py` 中非法 state / 非法 field 两个用例通过
  - 依赖：T1.1 —— 规模：S

- [x] **T1.3 引擎求值顺序** ✅ 2026-11-06
  - 文件：`meta/services/field_policy_engine.py`
  - 内容：`PolicyContext.state`；新增 `_state_policy()`（hidden > readonly > required）；`is_field_editable` / `is_field_visible` / `is_field_required` 均在系统字段判断后优先命中矩阵
  - 验收：单测覆盖矩阵只读压过默认、required 生效、hidden 阻断三者、未声明回落、系统字段 —— 全部通过
  - 依赖：T1.1 —— 规模：M

- [x] **T1.4 拦截器注入 state** ✅ 2026-11-06
  - 文件：`meta/services/field_policy_validation.py`（实际求值入口；`field_policy_interceptor.py` 只是 40 行包装器，无需改）
  - 内容：`_build_context` 注入 `PolicyContext.state`；新增 `_resolve_state_field()` 从 `RuleType.STATE_TRANSITION` 的 `state_field` 解析，不硬编码 `status`
  - 验收：`test_state_field_matrix.py` 覆盖 write 路径；`test_field_policy.py`(48) + `test_field_policy_interceptor.py`(16) 全绿
  - 依赖：T1.3 —— 规模：S

- [x] **T1.5 试点 schema + 回归** ✅ 2026-11-06
  - 文件：`meta/schemas/purchase_order.yaml`
  - 内容：声明 5 个状态（draft/submitted/confirmed/closed/cancelled）+ 3 组矩阵（confirmed 冻结源头要素 11 字段、closed 整单只读 13 字段、cancelled 禁止改抬头要素 4 字段）；`cancelled` 原因必填未做（该对象无取消原因字段，不虚构字段）
  - 验收：`test_state_field_matrix.py`（8 用例，含读真实 YAML 断言 5 状态与矩阵字段）全通过；与采购 schema/guard 合并跑 55 passed
  - 依赖：T1.4 —— 规模：M

## 阶段 2：S2 类型规格别名（P0，二次确认后收窄）

> 二次确认：字段组复用已由 `aspects.yaml`/`shared_properties.yaml` 承担，语义类型已存在；**不引入 DDIC 三层**，只加规格别名。

- [x] **T2.1 `_type_specs.yaml` 与合并逻辑** ✅ 2026-11-06
  - 文件：新建 `meta/schemas/_type_specs.yaml`；`meta/core/yaml_loader.py`（`load_type_specs` + `parse_field` 合并）
  - 内容：4 个 spec（code_32 / code_64 / name_64 / description_1024）；合并优先级 字段 > spec > 默认；未知 spec 启动失败；`_` 前缀文件不进 BO 扫描
  - 实现偏差：**未新增 `MetaField.type_spec` 字段**——合并发生在 `parse_field` 的 YAML dict 层（`data = {**_spec, **data}`），下游 `MetaField` / DDL / API / 前端零改动，比新增模型字段更小
  - 验收：`meta/tests/test_type_spec_merge.py`（4 用例）全绿（继承 / 字段覆盖 / 未知 spec 报错 / 仓库自带 spec 加载）
  - 依赖：T0 —— 规模：M

- [x] **T2.2 DDL 等价性证明** ✅ 2026-11-06
  - 文件：`meta/schemas/generated_schema.sql`（生成物）
  - 内容：备份 → `python -m meta.tools.sync_schema` 重新生成 → `git diff --stat -- meta/schemas/generated_schema.sql` **无输出（DDL 完全等价）**
  - 验收：diff 为空；启动日志确认 `Loaded 4 type_specs`、`_type_specs.yaml` 未被注册为 BO、`aspects.yaml` 被跳过
  - 依赖：T2.1 —— 规模：S

## 阶段 3：S3 扩展字段通用接入（P2，需 D3；二次确认后降级）

> 二次确认：扩展属性体系（四层 + `attribute_scopes` + `value_domain_type` + 三张值表）已完整，**不再新建通用 EAV 表 / 不做迁移**。

- [x] **T3.1 值表按约定派生** ✅ 2026-11-06
  - 文件：`meta/services/attribute_value_service.py`
  - 内容：新增 `for_object(object_type, data_source)`——按对象 id 派生 `<object_type>_attribute_values` / `<object_type>_id`；item / batch 走专用子类（延迟导入，避免循环依赖）；party / item / batch 三张现存表名称完全不变
  - 实现偏差：约定基准是**对象 id** 而非 `table_name`——`parties` 去复数会得到 `partie`，只有对象 id 是稳定单数
  - 验收：`test_attribute_value_service_factory.py` 4 用例 + `test_attribute_dictionary.py` 55 用例 → **59 passed**

- [x] **T3.2 通用 API 读取扩展字段** ✅ 结论：**已具备，无需改代码**
  - 实证：`party_attribute_values` / `item_attribute_values` / `batch_attribute_values` 三张值表本身都有 schema YAML，作为普通 BO 走 `GET /api/v2/bo/<object>_attribute_values`（列表/详情/筛选/权限全通用）；「扩展字段进通用路径」= 新对象加一份 `<object>_attribute_values.yaml` + 建表，属按对象接入，不是引擎缺口
  - 因此不新建猜测性 schema（D3 已定 item 试点延后）；新对象接入时按 `attribute_value_service.for_object()` 约定命名即可
  - 依赖：T3.1 —— 规模：0（原估 M 下调）

## 阶段 4：S5 影响分析 / S6 编号管理（P1，可并行）

- [x] **T5.1 影响分析服务** ✅ 2026-11-06
  - 文件：新建 `meta/services/meta_impact_service.py`；`meta/api/bo_api.py`（`meta_v2_bp` 加 `GET /api/v2/meta/impact`）
  - 内容：从 registry 反查 12 类引用（rule / state_transition / state_field_policy / relation / index / query / view / value_help / cascade_select / deletion_policy / change_event / action），字段名按独立标识符匹配（`id` 不误命中 `item_id`）
  - 实现偏差：路由放在 `bo_api.py` 的 `meta_v2_bp`（`/api/v2/meta` 的真实载体），而非 `meta_api.py`（那是 `/api/v1/meta`）
  - 验收：`meta/tests/test_meta_impact_service.py` 7 用例全绿（含 `purchase_order.status` 真实 schema 冒烟）；`test_api_v2_consumer_scenarios.py` 30 passed / 4 skipped
- [x] **T6.1 编号外部校验与管理面** ✅ 2026-11-06
  - 文件：`meta/services/document_number_service.py`（新增 `validate_external_number` + 4 个内部助手）、`meta/api/bo_api.py`（取号前挂外部号校验；`meta_v2_bp` 加 `GET /api/v2/meta/number-sequences`）
  - 内容：外部号四道检查（格式正则 / 起始值 / 位数上限 / 唯一性），错误码 `NUMBER_FORMAT_INVALID` / `NUMBER_OUT_OF_RANGE` / `NUMBER_DUPLICATE` / `NUMBER_SEQUENCE_UNAVAILABLE` / `NUMBER_TABLE_UNRESOLVED`；只读区间查询返回 `used` / `remaining` / `capacity`，`on_exhaust=error` 按 `{SEQ:n}` 上限算剩余，`extend` 返回 null
  - 实现偏差：**`NUMBERING` 保留为显式声明，未改为从 `number_sequences` 推导**——表里没有「对象 → 编号列/日期列」的映射，硬推导只能靠业务键/字段名猜测（如 `business_key[0]`），属隐式约定；改为在 `/number-sequences` 响应里暴露 `numbering` 声明，加单据类型仍是显式一行
  - 验收：`test_external_document_number.py` 8 用例全绿（格式不符 / 低于起始值 / 重复 / 自身更新排除 / extend 允许更长 / error 超位数 / 未绑序列 / 未声明对象）；`test_document_number_service.py`(7) + `test_api_v2_consumer_scenarios.py`(30 passed/4 skipped) 回归通过

## 阶段 5：S4 值集统一（P2，暂不做，仅记录）

- [x] **T4.1 值集统一（技术债记录）** ✅ 已留档，不实施 —— 结论：保持两套并行（主字段 `enum_filter`/`cascade_select`/`value_help`，扩展 `value_domain_type`）—— 规模：0

## 阶段 6：P2 策略清单与小修（只出清单，不实现）

- [x] **T7.1 保留/归档策略清单 + 落地** ✅ 2026-11-06 定策 / 2026-11-07 实施 —— 产出：`spec.md` 附录 A（按代码校准：audit_logs 分类 730/365/90 天 + 180 天归档宽限、change_events 365 天、document_revisions 24 个月、事实单据永久在线）—— 状态：**用户已确认并实施**：审计归档删除安全修复 `b1d1d551`、change_events 保留期 `345b125f`（v228 迁移 + `archive_change_events.py`）；`document_revisions` 归档脚本仍待建
- [x] **T7.2 多语言字段标签评估** ✅ 2026-11-06 —— 结论：**延后**（`ui.i18n_key` 已贯通，翻译资源属前端 i18n 资产；后端不建 `_TL`/`_VL` MLS 表），已写入 `spec.md` §7 明确不做表
- [x] **T7.3 `_template.yaml` 启动期过滤（G12）** ✅ 已在当前 HEAD 修复（无需改动）—— 证据：`yaml_loader.py:2889-2891` 已有 `if yaml_file.name.startswith("_"): continue`；本轮 `sync_schema` 启动日志确认 `_` 前缀文件被跳过 —— 规模：0

## 阶段 7：S7 事实单据平台能力（P0-单据，二次核实后重排，**本轮开工**）

> 前置：S1 已合并（`state_field_policies` 已在 main）。S7 全部以 `document_profile is None` 保证存量零影响。
> **二次核实结论**：原 T8.2（角色矩阵）/ T8.3（新建 reference 表）/ T8.4（三个 Hook）均有既有实现可复用，已按证据重排为「接线 + 小增量」。
> **用户裁定（2026-11-06）**：D7/D8/D9 为待定项 → 会计期间、修订族谱、元数据快照回滚**移出本轮**。
> 工作树：`D:\filework\s7-worktree`（`agent/s7-doc`，基线 `main@a1e3fc08`）。细则见 `spec.md` §9.1。

- [x] **T8.1 单据类型六件套声明（G13）** —— 规模 M
  - 文件：`meta/core/models.py`（`MetaDocumentProfile` + `MetaObject.document_profile=None`）、`meta/core/yaml_loader.py`（`parse_document_profile` + 5 项 fail-fast，`[S7]` 前缀）、新建 `meta/services/document_profile_service.py`（`get_profile` / `require_profile` / `is_posting_state`）、`meta/schemas/purchase_order.yaml`（`document:` 段）
  - 试点值：`order_no` / `order_date` / `status` / `posting_state=confirmed` / `document_type_id` / `line_object=purchase_order_line` / `line_parent_field=order_id` / `line_sequence_field=line_no`
  - 偏差：用 `line_object + line_parent_field` 替代原 `header_line_relation`（PO 无反向 1:N relation）
  - 验收：`meta/tests/test_document_profile.py` 5 用例通过；存量对象 `document_profile is None`
  - 依赖：无 —— P0

- [x] **T8.2 字段策略角色维度接线（G14，不改模型）** —— 规模 M
  - 文件：`meta/services/field_policy_engine.py`（补 `safe_evaluate` import，修 `when_expr` 恒 False 缺陷；`_role_policies` + `register_role_policy`；角色规则插在状态矩阵之前）、`meta/core/yaml_loader.py`（`obj.field_policies`）、`meta/api/bo_api.py`（2 处 `PolicyContext` 补 `user_context` + `_current_user_roles()`）、`meta/services/field_policy_validation.py::_build_context`（转 `UserContext`）
  - 求值顺序：系统字段 → 角色规则（未命中视为无意见）→ 状态矩阵 → 字段级 determination → ui 默认
  - 验收：`meta/tests/test_field_policy_role.py` 4 用例；`test_field_policy.py`(48) 不回归
  - 依赖：T8.1 —— P0

- [x] **T8.3 修订：过账强制快照（G15，不新建表）** —— 规模 M
  - 已完成：`revision_service.record(forced=False)`；`action_executor` 进入 `posting_state` 写无差异快照；`bo_api` 新增 `GET .../revisions/<n>`（列表接口 `GET .../revisions` 由既有 IF-001 提供，未重复新增）
  - 偏差：`document_type_field` / `snapshot_fields` 的存在性校验挪到 `validate_document_profiles()`（切面合并后），否则直接 `parse_meta_object` 原始 YAML 会被 aspect 提供的字段误判
  - 不做（拆出，见下）：14 单据全量启用 `revision_policy` + `revision_no` 迁移
  - 验收：`meta/tests/test_document_revision_posting.py` 5 用例；`test_revision_*.py` 不回归
  - 依赖：T8.1 —— P0

- [x] **T8.3-b 版本跟踪范围收敛：仅主数据 `item`**（2026-11-07 决策，原「14 单据全量启用」取消）
  - 决策依据：SAP / Oracle Fusion 的 version/revision 只覆盖主数据（SAP 物料修订级别、Oracle PLM 物料 revision），事务单据只做字段级审计（CDHDR / Manage Audit Policies），不存在整单版本；对齐全量 14 单据反而超出行业惯例
  - 落地：`items.yaml` 补 `revision_no` 字段 + `revision_policy`（enabled、diff 字段白名单、`require_reason: false`）；`v229__item_revision.py` 给存量 `items` 表补列 + 索引；`generated_schema.sql` 已重生成
  - 存量：`sales_order` 的 revision_policy **保留不动**（2026-10-29 PM 批准，已有版本数据与测试）；其余 12 个单据不启用（原描述「13 个对象缺列」实际为 12 个，`sales_orders` 早已有 `revision_no`）
  - 影响：主数据内容变更产生整单快照；状态字段变更也计入 diff（`status` editable=false）；纯时间戳/审计字段不推进版本（`NON_CONTENT_FIELDS`）

- [x] **T8.5 其余 13 个事实单据补 `document:` 声明** —— 规模 M（纯 YAML）
  - 逐个对照六特征填写；不确定 `posting_state` 的对象留空（= 不强制快照），不猜测
  - 验收：加载全部 schema 无 `[S7]` 报错；抽查 3 个单据 `require_profile` 通过
  - 依赖：T8.1 —— P0

- [x] **T8.4（部分）生命周期默认推导** —— 规模 S
  - 文件：新建 `meta/services/document_invariants.py`（`derive_default_state_policy()` / `derive_deletability()`，仅在未显式声明 `state_field_policies` 时兜底）
  - 会计期间部分**不做**（D7 待定）
  - 验收：`meta/tests/test_document_invariants.py`
  - 依赖：T8.1 —— P1

- [~] **T8.4（会计期间）** —— **暂缓（D7 待定）；二次确认：复用 G15 的 `fiscal_period`（`fiscal_periods`），不新建 `accounting_period`，需补 `document_profile.period_field`**
- [~] **T8.6 元数据版本快照与回滚（G18）** —— **暂缓（D9 待定）；二次确认：元数据未落 DB，原「一键回滚」删除，降级为 P2「只读快照 + diff」，回滚走 git + `sync_schema.py --execute`**

## 阶段 8：ERP 对标补齐（2026-11-07，worktree `D:\filework\s7-worktree`）

> 背景：完成 SAP / Oracle Fusion + D365 / NetSuite / Epicor / Infor / IFS / Workday / Odoo / Sage X3 / BC 横向调研后，只落地「行业通行、且现有模型可低成本承载」的三项；不做结构性重写。

- [x] **T9.1 无单收货（unordered receipt）** —— 对标 Oracle「Allow unordered receipts」+ 物料 `AllowUnorderedReceiptsFlag` 双开关；SAP 501/511
  - schema：`receipt.yaml` 的 `source_doc_type` 追加 `unordered`（`source_doc_id` 填 0，沿用平台「0 = 无引用」约定）；新增 `received_from_party_id` / `reason_code`；`items.yaml` 新增 `allow_unordered_receipt`（默认 false）
  - 服务：`receipt_service` 新增 `prepare_unordered_header` / `_validate_unordered_line` / `_post_unordered` / `_unordered_enabled` / `_assert_item_unordered_allowed`；不写计划行、不建需求分配；过账写 `RCV_UNORDERED`；红冲复用 `_create_direct_reversal_document(source_type=unordered)`
  - 迁移：`v230__unordered_receipt.py`（`receipts` 两列、`items` 一列、`inventory_adjustment_lines` 两列、移动类型 `RCV_UNORDERED`、参数定义 `allow_unordered_receipt` 默认 0、权限 `receipt:receipt_unordered`）
  - 验收：`meta/tests/test_receipt_unordered.py` 10 用例；收货 / 调整相关 109 用例回归全绿
  - 双开关 fail-closed：参数或物料开关读取异常 / 缺失一律按关闭处理

- [x] **T9.2 库存调整费用归属** —— 对标 SAP 201/551 账户分配、Oracle Misc Issue Distribution Account
  - schema：`inventory_adjustment_line.yaml` 新增 `cost_center_id` / `expense_account_code`
  - 守卫：`qty_decrease` / `scrap` 行必填，否则 `INV_EXPENSE_ATTRIBUTION_REQUIRED`；`_insert_line_from` 同步持久化
  - 验收：`test_inventory_adjustment_service.py` / `test_serial_adjustment_count_posting.py` 通过

- [x] **T9.3 `work_order` 放开 MTS（make-to-stock）** —— 对标 SAP 生产订单无销售订单来源、Oracle Discrete「Discrete Job without Sales Order」
  - schema：`work_order.yaml` 的 `order_id` / `order_line_id` 改 `nullable: true`；`source_demand_type` 追加 `manual`（手工备货 MTS）；新增 `item_id`（产出物料）/ `planned_qty`（计划数量）
  - 服务：`work_order_service` 新增 `SOURCE_DEMAND_MANUAL` 与 `_prepare_production` / `_prepare_manual` / `validate_production_create`；manual 禁 `source_demand_id` / `order_id` / `order_line_id` / `schedule_id`，必填 `item_id` + `planned_qty > 0`（`ST_ITEM_REQUIRED` / `ST_QTY_REQUIRED` / `ST_QTY_INVALID`）；`_insert` 对新列做缺列 fail-open
  - CRUD：`ProjectTaskGuardInterceptor` 在 `crud_create` 走生产建单前置校验并回填推导字段（`order_id` / `order_line_id` / `item_id` / `planned_qty`），`after_action` 复用 `expand_components` 后置展开组件
  - 迁移：`v231__work_order_mts.py`（放宽 `order_id` / `order_line_id` NOT NULL 的 12-step 重建 + 新增两列 + `idx_work_order_source_demand` 兜底 + verify / rollback）
  - 顺带修复：`project_task` 来源工单 `order_id=None` 在真实库 `NOT NULL` 下的 `IntegrityError`
  - 验收：`meta/tests/test_work_order_mts.py` 12 用例、`meta/tests/test_migration_v231.py` 3 用例；`test_work_order_production.py` / `test_work_order_service.py` / `test_receipt_service.py` / schema 生成器回归全绿


---

## 完成标准（Definition of Done）

1. 每条任务的测试用 `test.py --file` 跑通，并在本文件勾选。
2. 不改存量行为：S1/S2 默认空配置时，全部存量测试与改造前一致。
3. DDL 无意外变更（S2 等价性 diff 为空；S3 只新增表）。
4. 每条缺口在 `spec.md` §5 标注状态（已补 / 延后 / 不做）。
5. 不触碰主仓其他会话的改动；不新建与 v2xx 冲突的迁移号。

---

## 验证记录（2026-11-06，worktree `D:\filework\bo-meta-worktree`，分支 `agent/bo-meta`）

| 批次 | 命令 | 结果 |
|---|---|---|
| 新增用例 | `test.py --root <wt> --file meta/tests/test_state_field_matrix.py,meta/tests/test_type_spec_merge.py` | **12 passed / 0 failed** |
| 采购域回归 | 同上 + 采购 schema/guard 相关用例 | **55 passed** |
| 字段策略 + YAML 回归 | `test_field_policy.py`(48) + `test_field_policy_interceptor.py`(16) + `test_yaml_loader.py`(46) + `test_yaml_single_source_of_truth.py` | **116 passed / 10 failed** |
| 元数据 API 回归 | `test_metadata_completeness.py` + `test_metadata_driven_validator.py` + `test_meta_api.py` | **77 passed / 1 skipped** |
| DDL 等价 | `python -m meta.tools.sync_schema` + `git diff --stat -- meta/schemas/generated_schema.sql` | **diff 为空** |

**关于 10 项失败（既有基线，与本次改动无关）**：`test_yaml_single_source_of_truth.py` 的失败依赖 `role.yaml` / `user_group` 等对象在 HEAD 不存在（该测试文件最后一次改动 `958c3d82 feat(bo-action-v3): baseline snapshot`），属主仓既有问题；本次两组新用例与元数据 API 全绿。

**未提交改动清单**（worktree，9 项）：

```
M  meta/core/models.py
M  meta/core/yaml_loader.py
M  meta/schemas/.schema_version.json
M  meta/schemas/purchase_order.yaml
M  meta/services/field_policy_engine.py
M  meta/services/field_policy_validation.py
?? meta/schemas/_type_specs.yaml
?? meta/tests/test_state_field_matrix.py
?? meta/tests/test_type_spec_merge.py
```

`.schema_version.json` 的大 diff 来自「HEAD 与生成器基线差异」（字段清单/hash 全量重算），非本次 S1/S2 引入；随提交带上即可与 `generated_schema.sql` 保持成对一致。

---

## 二次检查补充（2026-11-06，commit 前复审）

对已交付代码逐项复审，补 4 项（均已通过测试）：

| # | 位置 | 问题 | 修复 |
|---|---|---|---|
| 1 | `yaml_loader._validate_state_declarations`（对应 T1.2） | 原校验只覆盖矩阵 key / 字段存在，状态目录自身无校验，且无矩阵时提前 return | 新增 5 条 fail-fast：空 code / 重复 code / category 白名单（initial / normal / terminal / system）/ transition 的 from-to 必须在 states 目录内（跳过 `""` 与 `"*"`）/ 矩阵 key 与字段（原 2 条）；无矩阵时也校验状态目录 |
| 2 | `meta_impact_service._change_event_refs`（对应 T5.1） | `track_fields` / `payload` 挂在 `ChangeNotificationConfig.events` 的每个 event 上，原实现从顶层读取 → 变更事件引用永远漏报 | 改为遍历 `events`，ref_id 形如 `change_notification:<event.type>`；新增用例 `test_change_event_refs_live_on_event`，summary 白名单补 `change_event` |
| 3 | `bo_api.get_object_schema`（对应 T1.1-T1.5 的前端可达性）| `/schema` 不下发 S1 配置，前端拿不到状态目录与矩阵 | 下发 `states` / `state_field_policies` |
| 4 | `bo_api.get_field_policies`（对应 T1.3/T1.4 的查询路径）| 接口不接 `state`，矩阵仅写路径生效，前端切换状态后重查无效 | 支持 `?state=`，注入 `PolicyContext(state=...)` |

验证：`test_state_field_matrix.py`(11) + `test_meta_impact_service.py`(8) + `test_yaml_loader.py`(46) = **65 passed / 0 failed / Exit 0**。

**已知遗留（有意不改）**：`AttributeValueService.for_object()` 尚无调用点，`attribute_guard_interceptor.py:100` 仍用 `AttributeValueService(context.data_source)` 走 party 默认表；`GUARDED_OBJECTS` 是固定白名单，新对象接入 guard 时才切工厂，此处改动会改变存量行为，故保留。
