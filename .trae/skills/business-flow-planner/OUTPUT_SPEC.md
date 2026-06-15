# business-flow-planner - OUTPUT_SPEC

## 输出文件

`{feat_dir}/business-flow.yaml`

## Schema 校验

必须满足 `.trae/specs/templates/business-flow.schema.json`

## 必含字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `review_status` | enum(draft/reviewed/approved) | PM/BA review 状态 |
| `agent_draft` | boolean | 是否 AI 起草 |
| `actor` | string | 业务角色 |
| `goal` | string | 业务目标 |
| `tasks` | array | 业务原子动作列表(≥1) |
| `questions` | array | 业务断言列表(≥1) |
| `preconditions` | array | 前置条件 |
| `data_tables` | array | 测试数据 |
| `cleanup` | object | 清理策略 |

## 任务 ID 命名规范

- `T_{DOMAIN}_{OBJECT}_{SEQ}` 例如 `T_BIZ_BO_001`
- DOMAIN 域缩写: BIZ(业务对象)/ENM(枚举)/AUD(审计)/EXP(导入导出)/PRD(产品版本)
- SEQ 3 位数字

## 规则 ID 命名规范

- `BR-{object_id}-{TYPE}-{field?}`
- TYPE: DEL/AUTH/AUDIT/KEY/CS/ASPECT/CASCADE_DEL/OWNER/FV

## 质量门禁

| 指标 | 目标 | 校验 |
|------|------|------|
| 业务规则派生覆盖率 | ≥ 80% | `discover_business_rules.py` 输出 |
| 业务断言比例 | ≥ 70% | YAML questions / (questions + DOM asserts) |
| 跨页路由数 | ≥ 3 | tasks 的 page_flow 字段 |
| Happy path 场景 | ≥ 1 | tasks 主路径 |
| Error path 场景 | ≥ 1 | tasks 错误路径 |
