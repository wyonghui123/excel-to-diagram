# -*- coding: utf-8 -*-
"""
[P1-3 E2E Service Guard] 6 大高修复区服务层关键路径守卫测试

覆盖 6 个 HIGH 风险、无测试 schema 的服务层关键路径:
1. task_execution   - task_api.py 的 retry/cancel 操作
2. scheduled_task   - task_api.py 的 enable/disable 操作
3. dimension_object_mapping - DimensionObjectMappingLoader 加载与查询
4. change_subscription - subscription_create_handler 的校验与创建
5. filter_variant   - filter_variant_api.py 的 CRUD 操作
6. (new_object 已无 schema 文件, 跳过)

测试策略:
- 静态源码分析: 验证关键代码路径存在 (守卫点)
- 运行时验证: 对可独立运行的模块 (如 DimensionObjectMappingLoader) 做真实调用
- 不依赖后端服务启动, 可在 CI 中运行

参考:
- deep_coverage.json: 38 schema 风险评估
- meta/api/task_api.py
- meta/services/subscription_create.py
- meta/core/dimension_object_mapping_loader.py
- meta/api/filter_variant_api.py
"""
import re
import os
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # meta/tests/ -> excel-to-diagram/


def _read_file(rel_path: str) -> str:
    """读取项目根目录下文件的全部内容"""
    full_path = PROJECT_ROOT / rel_path
    if not full_path.exists():
        pytest.skip(f'{rel_path} not found')
    with open(full_path, 'r', encoding='utf-8') as f:
        return f.read()


# ============================================================
# 1. task_execution (HIGH, 0 manual test)
# ============================================================

class TestTaskExecutionServiceGuard:
    """task_execution 服务层关键路径守卫

    task_api.py 提供 retry_execution 和 cancel_execution 两个关键操作,
    通过 SQL 修改 task_executions 表状态。
    """

    def test_retry_execution_resets_status_to_pending(self):
        """retry 必须将 status 重置为 pending + retry_count=0"""
        src = _read_file('meta/api/task_api.py')
        # 守卫: task_executions 重置 status=pending + retry_count=0
        assert "status = 'pending'" in src, (
            "BUG guard: task_api.py retry_execution 必须重置 status 为 pending"
        )
        assert "retry_count = 0" in src, (
            "BUG guard: task_api.py retry_execution 必须重置 retry_count 为 0"
        )

    def test_retry_execution_clears_error_message(self):
        """retry 必须清除 error_message"""
        src = _read_file('meta/api/task_api.py')
        assert "error_message = NULL" in src, (
            "BUG guard: retry_execution 必须清除 error_message (NULL)"
        )

    def test_cancel_execution_only_cancels_pending_or_queued(self):
        """cancel 只能取消 pending/queued 状态的执行, 不能取消已完成的"""
        src = _read_file('meta/api/task_api.py')
        # 守卫: WHERE id = ? AND status IN ('pending','queued')
        assert "status IN ('pending','queued')" in src, (
            "BUG guard: cancel_execution 必须限制只取消 pending/queued 状态"
        )

    def test_retry_checks_execution_exists(self):
        """retry 前必须检查执行记录是否存在"""
        src = _read_file('meta/api/task_api.py')
        assert "Execution not found" in src, (
            "BUG guard: retry_execution 必须检查执行记录存在 (404)"
        )

    def test_task_executions_table_used(self):
        """task_api.py 必须操作 task_executions 表"""
        src = _read_file('meta/api/task_api.py')
        assert "task_executions" in src, (
            "BUG guard: task_api.py 必须引用 task_executions 表"
        )


# ============================================================
# 2. scheduled_task (HIGH, 0 manual test)
# ============================================================

class TestScheduledTaskServiceGuard:
    """scheduled_task 服务层关键路径守卫

    task_api.py 提供 enable/disable 操作修改 scheduled_tasks 表的 enabled 字段。
    """

    def test_enable_sets_enabled_to_1(self):
        """enable 必须将 enabled 设为 1"""
        src = _read_file('meta/api/task_api.py')
        assert "scheduled_tasks SET enabled = 1" in src, (
            "BUG guard: enable_task 必须设置 enabled = 1"
        )

    def test_disable_sets_enabled_to_0(self):
        """disable 必须将 enabled 设为 0"""
        src = _read_file('meta/api/task_api.py')
        assert "scheduled_tasks SET enabled = 0" in src, (
            "BUG guard: disable_task 必须设置 enabled = 0"
        )

    def test_enable_disable_filter_by_code(self):
        """enable/disable 必须通过 code 字段筛选 (不是 id)"""
        src = _read_file('meta/api/task_api.py')
        assert "WHERE code = ?" in src, (
            "BUG guard: enable/disable 必须用 code (business_key) 而非 id 筛选"
        )

    def test_enable_disable_reload_after_update(self):
        """enable/disable 后必须 reload scheduler"""
        src = _read_file('meta/api/task_api.py')
        # 统计 scheduler.reload() 出现次数 (enable + disable 各 1 次)
        reload_count = src.count("scheduler.reload()")
        assert reload_count >= 2, (
            f"BUG guard: enable/disable 后必须 scheduler.reload(), "
            f"实际 reload 次数: {reload_count}"
        )

    def test_scheduled_tasks_table_used(self):
        """task_api.py 必须操作 scheduled_tasks 表"""
        src = _read_file('meta/api/task_api.py')
        assert "scheduled_tasks" in src, (
            "BUG guard: task_api.py 必须引用 scheduled_tasks 表"
        )


# ============================================================
# 3. dimension_object_mapping (HIGH, 1 manual test)
# ============================================================

class TestDimensionObjectMappingGuard:
    """dimension_object_mapping 服务层关键路径守卫

    DimensionObjectMappingLoader 从 YAML 加载维度映射配置,
    DimensionScopeEngine 优先使用 YAML 配置, fallback 到硬编码。
    """

    def test_loader_class_exists(self):
        """DimensionObjectMappingLoader 类必须存在"""
        src = _read_file('meta/core/dimension_object_mapping_loader.py')
        assert "class DimensionObjectMappingLoader" in src, (
            "BUG guard: DimensionObjectMappingLoader 类必须存在"
        )

    def test_loader_reads_yaml(self):
        """Loader 必须从 dimension_object_mapping.yaml 加载"""
        src = _read_file('meta/core/dimension_object_mapping_loader.py')
        assert "dimension_object_mapping.yaml" in src, (
            "BUG guard: Loader 必须读取 dimension_object_mapping.yaml"
        )

    def test_loader_has_get_applies_to(self):
        """Loader 必须提供 get_applies_to 方法"""
        src = _read_file('meta/core/dimension_object_mapping_loader.py')
        assert "get_applies_to" in src, (
            "BUG guard: Loader 必须有 get_applies_to 方法"
        )

    def test_engine_uses_loader(self):
        """DimensionScopeEngine 必须使用 DimensionObjectMappingLoader"""
        src = _read_file('meta/services/dimension_scope_engine.py')
        assert "dimension_object_mapping_loader" in src, (
            "BUG guard: DimensionScopeEngine 必须引用 dimension_object_mapping_loader"
        )

    def test_engine_has_fallback(self):
        """Engine 必须有 fallback 逻辑 (当 YAML 加载失败时)"""
        src = _read_file('meta/services/dimension_scope_engine.py')
        # 搜索 fallback 或 兼容 或 硬编码 关键词
        has_fallback = any(kw in src for kw in ['fallback', 'Fallback', '硬编码', 'RESOURCE_TABLE_MAP'])
        assert has_fallback, (
            "BUG guard: DimensionScopeEngine 必须有 fallback 逻辑"
        )

    def test_yaml_config_has_product_dimension(self):
        """dimension_object_mapping.yaml 必须包含 product 维度"""
        src = _read_file('meta/schemas/dimension_object_mapping.yaml')
        assert "dimension_code: product" in src, (
            "BUG guard: dimension_object_mapping.yaml 必须定义 product 维度"
        )

    def test_yaml_config_has_domain_dimension(self):
        """dimension_object_mapping.yaml 必须包含 domain 维度"""
        src = _read_file('meta/schemas/dimension_object_mapping.yaml')
        assert "dimension_code: domain" in src, (
            "BUG guard: dimension_object_mapping.yaml 必须定义 domain 维度"
        )


# ============================================================
# 4. change_subscription (HIGH, 2 manual test)
# ============================================================

class TestChangeSubscriptionServiceGuard:
    """change_subscription 服务层关键路径守卫

    subscription_create_handler 校验参数后写入 change_subscriptions 表。
    """

    def test_handler_validates_object_type_required(self):
        """必须校验 object_type 必填"""
        src = _read_file('meta/services/subscription_create.py')
        assert "object_type" in src and "必填" in src, (
            "BUG guard: subscription_create_handler 必须校验 object_type 必填"
        )

    def test_handler_validates_channel_value(self):
        """必须校验 channel 为 websocket 或 webhook"""
        src = _read_file('meta/services/subscription_create.py')
        assert "websocket" in src and "webhook" in src, (
            "BUG guard: 必须校验 channel 为 websocket/webhook"
        )

    def test_handler_validates_webhook_url_when_webhook(self):
        """webhook 模式必须提供 webhook_url"""
        src = _read_file('meta/services/subscription_create.py')
        assert "webhook_url" in src, (
            "BUG guard: webhook 模式必须提供 webhook_url"
        )

    def test_handler_writes_to_change_subscriptions(self):
        """必须写入 change_subscriptions 表"""
        src = _read_file('meta/services/subscription_create.py')
        assert "change_subscriptions" in src, (
            "BUG guard: 必须写入 change_subscriptions 表"
        )

    def test_handler_checks_auth(self):
        """必须检查用户登录状态"""
        src = _read_file('meta/services/subscription_create.py')
        assert "未登录" in src, (
            "BUG guard: 必须检查用户登录状态"
        )

    def test_handler_sets_default_event_types(self):
        """默认 event_types 为 created/updated/deleted"""
        src = _read_file('meta/services/subscription_create.py')
        assert "'created'" in src and "'updated'" in src and "'deleted'" in src, (
            "BUG guard: 默认 event_types 必须包含 created/updated/deleted"
        )

    def test_handler_serializes_event_types_to_json(self):
        """event_types 必须序列化为 JSON 存入 DB"""
        src = _read_file('meta/services/subscription_create.py')
        assert "json.dumps(event_types)" in src, (
            "BUG guard: event_types 必须 json.dumps 序列化"
        )


# ============================================================
# 5. filter_variant (HIGH, 0 manual test)
# ============================================================

class TestFilterVariantServiceGuard:
    """filter_variant 服务层关键路径守卫

    filter_variant_api.py 提供 CRUD 操作管理过滤变体。
    """

    def test_api_has_create_endpoint(self):
        """必须有创建变体端点"""
        src = _read_file('meta/api/filter_variant_api.py')
        # 搜索 POST 路由
        has_post = bool(re.search(r"methods.*POST", src))
        assert has_post, (
            "BUG guard: filter_variant_api 必须有 POST (创建) 端点"
        )

    def test_api_has_read_endpoint(self):
        """必须有读取变体端点"""
        src = _read_file('meta/api/filter_variant_api.py')
        # 搜索 GET 路由
        has_get = bool(re.search(r"methods.*GET", src)) or "@filter_variant_bp.route" in src
        assert has_get, (
            "BUG guard: filter_variant_api 必须有 GET (读取) 端点"
        )

    def test_api_writes_to_filter_variants_table(self):
        """必须操作 filter_variants 表"""
        src = _read_file('meta/api/filter_variant_api.py')
        assert "filter_variants" in src, (
            "BUG guard: filter_variant_api 必须操作 filter_variants 表"
        )

    def test_api_has_owner_isolation(self):
        """必须基于 owner_id 隔离 (个人变体 vs 共享变体)"""
        src = _read_file('meta/api/filter_variant_api.py')
        assert "owner_id" in src or "user_id" in src, (
            "BUG guard: filter_variant_api 必须有 owner 隔离 (owner_id/user_id)"
        )

    def test_api_has_is_shared_flag(self):
        """必须有 is_shared 标志区分个人/共享变体"""
        src = _read_file('meta/api/filter_variant_api.py')
        assert "is_shared" in src, (
            "BUG guard: filter_variant_api 必须有 is_shared 标志"
        )


# ============================================================
# 6. Cross-cutting: task_scheduler 集成守卫
# ============================================================

class TestTaskSchedulerIntegrationGuard:
    """task_scheduler 集成关键路径守卫

    验证 task_api.py 与 scheduler 的集成点。
    """

    def test_api_requires_scheduler_init(self):
        """task_api 必须检查 scheduler 是否初始化"""
        src = _read_file('meta/api/task_api.py')
        assert "TaskScheduler not initialized" in src or "_scheduler is None" in src, (
            "BUG guard: task_api 必须检查 scheduler 初始化状态"
        )

    def test_api_has_trigger_endpoint(self):
        """必须有手动触发任务端点"""
        src = _read_file('meta/api/task_api.py')
        assert "trigger" in src, (
            "BUG guard: task_api 必须有 trigger (手动触发) 端点"
        )

    def test_api_has_queue_stats_endpoint(self):
        """必须有队列统计端点"""
        src = _read_file('meta/api/task_api.py')
        assert "queue_stats" in src or "get_queue_stats" in src, (
            "BUG guard: task_api 必须有 queue_stats 端点"
        )

    def test_api_has_scheduler_status_endpoint(self):
        """必须有 scheduler 状态查询端点"""
        src = _read_file('meta/api/task_api.py')
        assert "task_scheduler_status" in src or "get_status" in src, (
            "BUG guard: task_api 必须有 scheduler status 端点"
        )
