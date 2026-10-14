# SCHED_CRONTAB_RULES.md

> **Scheduled Task Cron 表达式规则文档**
> 版本: v1.1
> 创建: 2026-06-14
> BMRD DEFER ID: SCHED-CRONTAB-VALIDATION

## 1. 概述

Scheduled Task 使用标准 5 段 cron 表达式:
```
分 时 日 月 周
```

## 2. 字段范围

| 字段 | 范围 | 必填 |
|------|------|------|
| 分 (minute) | 0-59 | 是 |
| 时 (hour) | 0-23 | 是 |
| 日 (day) | 1-31 | 是 |
| 月 (month) | 1-12 | 是 |
| 周 (weekday) | 0-6 (0=周日) | 是 |

**必须 5 段** (与 Vixie cron / Quartz 风格一致)。

## 3. 语法

### 3.1 通配符 `*`
```cron
* * * * *      # 每分钟
```

### 3.2 步长 `*/n`
```cron
*/5 * * * *    # 每 5 分钟
0 */2 * * *    # 每 2 小时 (0:00, 2:00, 4:00, ...)
*/15 9-17 * * 1-5  # 工作日 9-17 点每 15 分钟
```

### 3.3 列表 `a,b,c`
```cron
0 8,12,18 * * *  # 每天 8:00, 12:00, 18:00
0 9 * * 1,3,5    # 周一/三/五 9:00
```

### 3.4 范围 `a-b`
```cron
0 9-17 * * *     # 每天 9:00-17:00 (整点)
30 8-18 * * 1-5  # 工作日 8:30-18:30 (半点)
```

### 3.5 组合
```cron
0 9,15 * * 1-5   # 工作日 9:00 和 15:00
*/30 9-18 * * *   # 9:00-18:59 每 30 分钟
```

## 4. 关键代码 (`meta/core/cron_parser.py`)

### 4.1 CronParser 类
```python
class CronParser:
    FIELD_NAMES = ['minute', 'hour', 'day', 'month', 'weekday']
    FIELD_RANGES = {
        'minute': (0, 59),
        'hour': (0, 23),
        'day': (1, 31),
        'month': (1, 12),
        'weekday': (0, 6),
    }
    
    def parse(self, expression: str) -> dict:
        # 5 段校验
        fields = expression.strip().split()
        if len(fields) != 5:
            raise ValueError(f"Invalid cron expression: {expression}")
        # ...
    
    def get_next(self, expression: str, after: datetime) -> Optional[datetime]:
        # 最多找 1460 天 (4 年) 内的下一次执行
        end_date = current + timedelta(days=1460)
        # ...
    
    def describe(self, expression: str) -> str:
        # 自然语言描述: "每分钟", "每天 09:30" 等
```

### 4.2 支持的特性
| 特性 | 支持 | 说明 |
|------|------|------|
| `*` | ✅ | 通配 |
| `*/n` | ✅ | 步长 |
| `a,b,c` | ✅ | 列表 |
| `a-b` | ✅ | 范围 |
| `L` (last) | ❌ | 不支持 (如 `L` = 当月最后一天) |
| `W` (weekday) | ❌ | 不支持 (如 `15W` = 离 15 号最近的工作日) |
| `#` (nth) | ❌ | 不支持 (如 `5#2` = 第二个周五) |
| `@yearly` 等别名 | ❌ | 不支持 |

**结论**: 实现**简化版 cron** (Vixie cron 风格), 不支持 Quartz 扩展。

### 4.3 Workflow 定时触发的 `trigger_expr` 契约

Workflow 定义中 `trigger_kind='schedule'` 时，`trigger_expr` **必须是 JSON 对象且含非空 `cron` 字段**（标准 5 字段 cron，口径同 §2 / §3）：

```json
{"cron": "0 9 * * 1-5"}
```

- **发布即校验**：`meta/core/workflow_trigger.py` 的 `parse_trigger_expr` → `_parse_schedule_expr` 负责解析；由 `publish_workflow` 的定义期闸门 `assert_trigger` 在**发布时**执行，非法即拒绝发布（不落定义行）。
- `manual` / `api` 不解释 `trigger_expr`（由调用方直接唤起 Run）。
- `event` 另有契约：JSON 对象 `{"event": "<事件名>", "when": "<可选条件>", "doc_ref": "<可选 payload 字段>"}`。

发布期拒绝的错误码（`WorkflowDefinitionError` / `DefinitionFinding`）：

| code | 触发条件 |
|------|----------|
| `TRIGGER_EXPR_MISSING` | `schedule` 但 `trigger_expr` 为空 |
| `TRIGGER_EXPR_NOT_JSON` | `schedule` 但非合法 JSON |
| `TRIGGER_EXPR_NOT_OBJECT` | `schedule` 但 JSON 非对象 |
| `TRIGGER_CRON_MISSING` | 缺非空 `cron` |
| `TRIGGER_CRON_INVALID` | `cron` 非法（`CronParser.parse` 抛 `ValueError`） |

### 4.4 Workflow 定时调度器 (`meta/core/workflow_schedule_scheduler.py`)

`WorkflowScheduleScheduler` 继承 `MaintenanceScheduler`，把**已发布** workflow 的 schedule 声明派生为 cron 作业并到点唤起 Run；作业集**从定义表派生**（非代码常量），与运维作业 / `platform_tick` 互不相交：

- 作业集来源：`list_latest_workflows(data_source, trigger_kind='schedule')`（每个 `workflow_key` 的最新版）；作业形状 `code=workflow_key`、`schedule=trigger_expr.cron`、`handler='workflow_schedule'`。
- `refresh_jobs(now)`：**增量**重派生 —— `schedule` 未变的 code 沿用旧 `_next_run`，新增 / 变更用 `CronParser.get_next(now)` 计算，消失的 code 删除；单条定义解析失败仅跳过并记 error，不拖垮整轮。
- `tick(now)`：**先 `refresh_jobs` 再 `super().tick`** —— 定义的新增 / 改版 / 删除在每轮自动生效，无需重启。
- `run_now(code)`：code 不在派生作业集 → `False`；否则调 `workflow_engine.start_run(data_source, workflow_key=code, trigger_kind='schedule')` 并返回 `True`。
- `is_registered(code)` / `codes()`：按派生作业集判定（覆盖基类的 handler 判定）。
- **调度状态（`_jobs` / `_next_run`）仅在内存**，不落 `scheduled_tasks` 表。

## 5. 数据库 Schema

### 5.1 scheduled_task 表 (`meta/schemas/scheduled_task.yaml`)
| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `trigger_mode` | string | 是 | `cron` | 触发模式 |
| `schedule` | string | 否 | - | Cron 表达式 (max_length 100) |
| `trigger_config` | json | 否 | - | 触发配置 (interval_seconds 等) |
| `handler` | string | 是 | - | 任务处理器名称 |
| `handler_config` | json | 否 | - | 处理器配置 |
| `queue` | string | 否 | - | 队列名 |
| `enabled` | bool | - | - | 是否启用 |

### 5.2 字段关系
- `trigger_mode = 'cron'` → 使用 `schedule` 字段
- `trigger_mode = 'interval'` → 使用 `trigger_config.interval_seconds`
- `trigger_mode = 'manual'` → 手动触发

## 6. 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v2/bo/scheduled_task` | GET | 列出任务 |
| `/api/v2/bo/scheduled_task` | POST | 创建任务 |
| `/api/v2/bo/scheduled_task/{id}` | GET | 任务详情 |
| `/api/v2/bo/scheduled_task/{id}/run` | POST | 立即运行 |
| `/api/v2/bo/scheduled_task/{id}/next` | GET | 下次执行时间 |

### 6.1 进程内调度器运维端点

运维作业（DB 维护 / 审计归档 / 导入队列）与任务域的 `platform_tick` 已迁到**进程内调度器**
（调度配置内嵌代码，不落 `scheduled_tasks` 表）。其运维入口由 `scheduler_bp` 提供，
**不受 `tasks` 模块开关影响，无条件注册**：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v2/schedulers/status` | GET | 两个调度器的作业清单 / 下次触发 / handler 就绪 / `paused` |
| `/api/v2/schedulers/{code}/run-now` | POST | 按需跑一次指定作业（未知 code → 404；无 handler → 409） |

遗留 `/api/v2/tasks/{code}/trigger|enable|disable` 对**已迁移作业码**返回 **409**
（`scheduled_tasks` 表已不承载其调度，改表改不动，不再假成功），提示改用上面的 `run-now`。

### 6.2 全局暂停开关 `CRON_JOBS_ENABLED`

| 取值 | 行为 |
|------|------|
| `1` / 未设置 | 正常：`MaintenanceScheduler`、`PlatformScheduler` 与 `WorkflowScheduleScheduler` 均启动 |
| `0` / `false` / `False` | **暂停全部 cron 作业**：三个进程内调度器都不启动 |

- 该开关**不依赖任何数据表**，故 `scheduled_tasks` 历史行清理后仍可作为「快速禁用」安全网。
- 暂停态下 `/api/v2/schedulers/status` 返回 `200` 且 `data.paused=true`（调度器数据为 `null`）；`/api/v2/workflows/scheduler/status` 同样返回 `200` 且 `paused=true`。
- 部署用法：设环境变量 `CRON_JOBS_ENABLED=0`（如 `.env` 或进程环境）。

### 6.3 Workflow 调度只读端点

`WorkflowScheduleScheduler` 由 server.py 在 cron 启用时随进程内调度器一并创建 / 启动，其只读查询经 `meta/api/workflow_api.py` 的 `workflow_bp` 暴露（**随 `tasks` 模块门控注册**，未启用 `tasks` 时不可用）：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v2/workflows/schedules` | GET | 只读聚合：已发布 schedule 定义（`workflow_key` / `name` / `version` / `node_count`）+ 触发规则（`cron` / `cron_label` / `next_run_at` / `scheduler_registered`）+ 最近 Run 派生状态（`runs`） |
| `/api/v2/workflows/scheduler/status` | GET | 调度器作业状态：未接线 `503`；暂停态 `200` + `paused=true`；正常 `200` + `{paused:false, jobs}` |

## 7. 校验规则

### 7.1 创建/更新时
- ✅ 5 段格式 (空格分隔)
- ✅ 每段在合法范围
- ✅ 步长 > 0
- ✅ 列表/范围语法正确

### 7.2 CronParser.parse() 抛错
```python
# 错误场景
parse('')              # ValueError: 段数错
parse('0 0 * *')       # ValueError: 段数错 (4 段)
parse('60 * * * *')    # ValueError: minute 越界
parse('0 24 * * *')    # ValueError: hour 越界
parse('0 0 32 * *')    # ValueError: day 越界
```

## 8. 常用 Cron 例子

| 表达式 | 含义 |
|--------|------|
| `0 0 * * *` | 每天 0:00 (午夜) |
| `0 9 * * *` | 每天 9:00 |
| `0 9 * * 1-5` | 工作日 9:00 |
| `0 0 1 * *` | 每月 1 日 0:00 |
| `0 0 1 1 *` | 每年 1 月 1 日 0:00 |
| `*/10 * * * *` | 每 10 分钟 |
| `0 */2 * * *` | 每 2 小时整点 |
| `0 9-18 * * *` | 9-18 点整点 |
| `30 8 * * 1` | 周一 8:30 |
| `0 8,12,18 * * *` | 每天 8/12/18 点 |

## 9. 已知限制

| 限制 | 原因 | 解决方案 |
|------|------|----------|
| 不支持 `L`/`W`/`#` | 实现简化 | 接受 Vixie cron 子集 |
| 不支持 `@yearly` 等别名 | 实现简化 | 用户用具体表达式 |
| 最多找 1460 天下次执行 | 性能 | 接受 (4 年足够) |
| 不支持时区 (默认服务器本地) | 设计 | 用 trigger_config.timezone |

## 10. BMRD 规则

| 规则 ID | 状态 | 说明 |
|---------|------|------|
| SCHED-1 | ACTIVE | scheduled_task 必填 |
| SCHED-2 | ACTIVE | schedule_type 校验 |
| SCHED-CRONTAB-VALIDATION | 🟢 解锁 (文档化完成) | 改 `_advanced_module_rules.yaml` 中 `SCHED-CRONTAB-VALIDATION` 为 ACTIVE |

## 11. 解锁条件

SCHED-CRONTAB-VALIDATION DEFER → ACTIVE:
- [x] 文档化完成 ✅
- [x] 关键代码确认 ✅ (CronParser 实现)
- [x] 端点确认 ✅ (scheduled_task 200 OK)
- [x] 数据库 schema 确认 ✅ (schedule 字段)
- [x] BMRD 规则引用 ✅
- [ ] 解锁: 改 `_advanced_module_rules.yaml` 中 `SCHED-CRONTAB-VALIDATION` 为 ACTIVE

## 12. 测试覆盖

- `meta/tests/test_cron_parser.py` - 核心解析
- `meta/tests/test_cron_parser_eng.py` - 英文解析
- `meta/tests/test_scheduled_tasks_comprehensive.py` - 综合
- `meta/tests/test_scheduled_tasks_e2e.py` - E2E
- `meta/tests/test_task_scheduler.py` - 调度器

## 13. 参考

- 后端核心: `meta/core/cron_parser.py` (CronParser 类)
- 后端任务: `meta/core/task_scheduler.py`
- 后端 API: `meta/api/task_api.py`
- Schema: `meta/schemas/scheduled_task.yaml`
- BMRD 规则: `.trae/specs/_business_rules/_advanced_module_rules.yaml`
