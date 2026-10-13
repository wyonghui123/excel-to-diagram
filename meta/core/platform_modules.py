# -*- coding: utf-8 -*-
"""
平台模块启用开关

【背景 2026-10-13 / roadmap v1.32.0 §6.2.4】
平台层模块（规则体系 / 任务体系等）位于 `meta/` 下，**不经过 `app_loader`**，
因此 `ENABLED_APPS` 管不到它们；blueprint 注册与菜单种子又都是无条件的。
本模块提供部署级启停能力。

【与 ENABLED_APPS 的关系 —— 两条正交轴】
    应用包 `apps/<id>/`  → ENABLED_APPS             白名单（选装，可为空）
    平台模块 `meta/`     → DISABLED_PLATFORM_MODULES 黑名单（默认全开）

【为什么是黑名单】
平台模块是"平台自带能力"，应当默认在场、按需关闭；新增模块默认开启 ⇒
存量部署不需要改任何配置（零风险）。

【用法】
    from meta.core.platform_modules import is_module_enabled

    if is_module_enabled('tasks'):
        app.register_blueprint(task_api_bp)

环境变量（设置即生效，逗号分隔）:
    DISABLED_PLATFORM_MODULES=tasks,rules
"""
import os
from threading import Lock

#: 环境变量名
ENV_DISABLED_PLATFORM_MODULES = 'DISABLED_PLATFORM_MODULES'

#: 已知平台模块 id —— 与 server.py 的 blueprint 注册、菜单种子一一对应。
#: 新增平台模块时在此登记（未登记的 id 也会被识别为"启用"，故登记只为可读性/自文档）。
KNOWN_PLATFORM_MODULES = (
    # 任务体系: task_api / task_inbox / task_decision 三个 blueprint + init_task_menus。
    # 注意 task_scheduler（调度器本体）**不受本开关控制** —— 它是共享基础设施，
    # 审计归档 / 导入队列 / DB 维护都挂在上面。关模块 != 关调度。
    'tasks',
    # 规则体系: **暂不可关闭** —— 无独立入口（无专属 blueprint / 无菜单种子）。
    #   meta/core/rule_*.py 是 BO 动作执行与索引管理的底层依赖
    #   （被 action_executor / models / index_management_service / cross_object_chain 直接 import），
    #   关掉等于关掉平台核心功能。
    #   注: meta/api/permission_rule_api.py 是**权限规则**（数据权限判定，权限矩阵依赖它），
    #   不是"规则体系"，且属权限基础设施，同样不可关。
    #   保留此 id 仅为将来规则体系获得独立入口时预留，届时需同时接线两个作用点。
    'rules',
)

#: 当前**真正可关闭**的模块 id —— 与 KNOWN_PLATFORM_MODULES 的区别是"有无可关闭入口"。
#: 写进黑名单但不在此集合里 = 无效果（不报错，属已知占位）。
CLOSABLE_PLATFORM_MODULES = ('tasks',)

_LOCK = Lock()
_CACHE = {}


def _get_disabled() -> frozenset:
    """解析环境变量 → 被禁用模块集合（每次进程生命周期内只解析一次）。"""
    with _LOCK:
        if 'disabled' not in _CACHE:
            raw = os.getenv(ENV_DISABLED_PLATFORM_MODULES) or ''
            _CACHE['disabled'] = frozenset(
                part.strip() for part in raw.split(',') if part.strip()
            )
        return _CACHE['disabled']


def is_module_enabled(module_id: str) -> bool:
    """平台模块是否启用（默认 True = 全开）

    Args:
        module_id: 模块 id，见 KNOWN_PLATFORM_MODULES

    Returns:
        bool: 不在 DISABLED_PLATFORM_MODULES 黑名单中即启用
    """
    return module_id not in _get_disabled()


def disabled_modules() -> frozenset:
    """当前被禁用的模块集合（供启动日志/诊断端点使用）"""
    return _get_disabled()


def ineffective_disables() -> frozenset:
    """被写入黑名单但**无可关闭入口**的模块 id。

    这些 id 写了不报错但**无效果** —— 部署时须知道，避免误以为已关闭。
    """
    return frozenset(_get_disabled() - set(CLOSABLE_PLATFORM_MODULES))


def clear_cache() -> None:
    """清空缓存（仅测试用：改了环境变量后需调用）"""
    with _LOCK:
        _CACHE.clear()