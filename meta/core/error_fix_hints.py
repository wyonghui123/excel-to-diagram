# -*- coding: utf-8 -*-
"""
[MODULE] 错误码 fix_hint 表 (v3.18 D.6/M.6)
[DESCRIPTION] 给 AI Coding Agent 直接消费的修复建议

使用:
  from meta.core.error_fix_hints import get_fix_hint

  hint = get_fix_hint('E001')  # → "检查 meta/api/auth.py:42 ..."

设计:
- 跟 ErrorCode 一一对应
- AI 自动推断 (v3.17 决策): 静态 fallback + 运行时从 stack trace 推断
- 见_also: 相关文件路径 (Agent 可用 grep 找)
"""
from typing import Optional


# [DECORATIVE] v3.18: fix_hint 表 (静态 + 文档化)
FIX_HINTS = {
    # 鉴权类
    'unauthorized': {
        'fix_hint': '检查 requests.Session() + dev-login 流程是否完成. 看 meta/api/auth.py:42 dev_login 实现.',
        'see_also': ['meta/api/auth.py', 'tests/fixtures/admin_token.py'],
    },
    'token_expired': {
        'fix_hint': 'Token 过期, 重新调 dev-login. 看 meta/services/token_service.py 寿命配置.',
        'see_also': ['meta/services/token_service.py'],
    },
    'token_blacklisted': {
        'fix_hint': 'Token 已失效 (logout/bump version). 重新 dev-login 即可.',
        'see_also': ['meta/services/token_version_service.py'],
    },
    'auth_service_error': {
        'fix_hint': '认证服务异常, 看 meta/services/auth_provider.py. 检查 DB 连接 + user 表.',
        'see_also': ['meta/services/auth_provider.py', 'meta/architecture.db'],
    },
    'forbidden': {
        'fix_hint': '权限不足. 检查 user.roles 和 permission. 看 meta/core/interceptors/permission_interceptor.py.',
        'see_also': ['meta/core/interceptors/permission_interceptor.py'],
    },
    'admin_required': {
        'fix_hint': '需要 admin 权限. 用 admin 用户登录, 或调整 action 的 role 要求.',
        'see_also': ['meta/api/bo_action_api.py'],
    },

    # Action 业务
    'action_not_found': {
        'fix_hint': 'Action 不存在. 检查 meta/services/bo_action_service.py action 注册, 或确认 action_id 拼写.',
        'see_also': ['meta/services/bo_action_service.py', 'meta/services/actions/'],
    },
    'action_validation_error': {
        'fix_hint': 'Action 参数验证失败. 看 meta/services/bo_action_service.py 的 schema. 确认输入字段类型/必填.',
        'see_also': ['meta/services/bo_action_service.py'],
    },
    'action_handler_error': {
        'fix_hint': 'Action handler 抛错. 看具体 message 和 stack trace, 找对应 handler 实现.',
        'see_also': ['meta/services/actions/'],
    },
    'action_params_missing': {
        'fix_hint': '必填参数缺失. 看 action schema (YAML/YAML service) 必填字段.',
        'see_also': ['meta/services/bo_action_service.py'],
    },
    'action_permission_denied': {
        'fix_hint': 'Action 权限拒绝. 看 permission_intersector 的 role/permission 规则.',
        'see_also': ['meta/core/interceptors/permission_interceptor.py'],
    },

    # Subflow
    'subflow_timeout': {
        'fix_hint': 'Subflow step 超时. 增加 timeout_ms 或优化 step 实现.',
        'see_also': ['meta/services/subflow_engine.py'],
    },
    'subflow_template_not_found': {
        'fix_hint': 'Subflow 模板不存在. 看 meta/api/subflow_api.py _subflow_template GET.',
        'see_also': ['meta/api/subflow_api.py'],
    },

    # DB
    'db_integrity_error': {
        'fix_hint': 'DB 完整性错误. 看具体 message, 通常是外键/唯一约束. 检查 SQL.',
        'see_also': ['meta/core/db/connection_pool.py'],
    },
    'db_locked': {
        'fix_hint': 'DB 锁. 等待或重试, 不要并发写. 看 connection_pool + WriteQueue.',
        'see_also': ['meta/core/db/connection_pool.py'],
    },
    'db_wal_too_large': {
        'fix_hint': 'WAL 文件 > 1MB. 跑 backup_db.py --check 或手动 checkpoint.',
        'see_also': ['scripts/backup_db.py', 'meta/core/db_health_monitor.py'],
    },

    # [v1.0.1] 权限 derivation 错码
    'parent_permission_denied': {
        'fix_hint': (
            '[v1.0.1 D9] 缺少父资源的 read 权限. env PARENT_READ_STRICT_MODE=true 升级触发. '
            '解决: 1) 给用户/角色授予 {parent}:read 权限, 或 2) 关闭 strict 模式. '
            '看 meta/core/interceptors/permission_interceptor.py:_check_parent_read_advisory.'
        ),
        'see_also': [
            'meta/core/interceptors/permission_interceptor.py',
            'meta/core/bo_yaml_cache.py',
            'docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.0.md',
        ],
    },
    'err_chain_read_denied': {
        'fix_hint': (
            '[v1.0.1 D10] 写子资源时链中任一 read 权限缺失 (env CHAIN_DERIVATION_STRICT_MODE=true 升级触发). '
            '解决: 1) 给 user/role 授予 chain 中任一 BO 的 read 权限, 或 2) 关闭 strict 模式. '
            '看 meta/core/interceptors/permission_interceptor.py:_check_chain_read.'
        ),
        'see_also': [
            'meta/core/interceptors/permission_interceptor.py',
            'meta/core/bo_yaml_cache.py:get_parent_chain',
            'docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.0.md#fr-003b',
        ],
    },
    'err_chain_instance_out_of_scope': {
        'fix_hint': (
            '[v1.0.1 D13] 写操作实例越权 — target 的 parent chain 中有 instance 不在 user data_scope 范围. '
            '解决: 1) 给 user 分配正确的数据权限 (覆盖 parent chain instances), '
            '或 2) 检查 target_id 是否合法, 3) 看 _resolve_parent_chain() 是否能正确解析 FK. '
            '实例级硬拒, 不是 audit-only.'
        ),
        'see_also': [
            'meta/core/interceptors/permission_interceptor.py',
            'meta/core/bo_yaml_cache.py:resolve_parent_chain',
            'docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.0.md#fr-003b2',
        ],
    },
}


def get_fix_hint(error_code: str) -> Optional[dict]:
    """[DECORATIVE] D.6: 查 fix_hint"""
    return FIX_HINTS.get(error_code)


def get_all_codes() -> list:
    """[DECORATIVE] M.6: 列出所有错误码 (用于 /_error_codes 端点)"""
    return list(FIX_HINTS.keys())


def get_codes_count() -> int:
    return len(FIX_HINTS)
