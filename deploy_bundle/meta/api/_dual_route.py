# -*- coding: utf-8 -*-
r"""
Dual Route Helper — v1/v2 双路由注册辅助

【背景 2026-06-04】
v1.4 修复：v1 路径加 v2 别名（保留 6 个月过渡期）
用 add_url_rule 一次注册 v1 + v2 路由（消除重复装饰器）

使用：
    from meta.api._dual_route import add_dual_routes
    add_dual_routes(permission_bp, '/permissions/explain', explain_permission, ['POST'])
"""
from typing import List, Callable
from flask import Blueprint


def add_dual_routes(
    bp: Blueprint,
    path_suffix: str,
    view_func: Callable,
    methods: List[str],
):
    """注册 v1 + v2 别名路由

    Args:
        bp: Flask 蓝图
        path_suffix: 不含 /api/v1/ 前缀的路径（如 '/permissions/explain'）
        view_func: 视图函数
        methods: HTTP 方法列表
    """
    # v1 路径
    bp.add_url_rule(
        f'/api/v1{path_suffix}',
        endpoint=f'v1_{view_func.__name__}',
        view_func=view_func,
        methods=methods,
    )
    # v2 路径（正式）
    bp.add_url_rule(
        f'/api/v2{path_suffix}',
        endpoint=f'v2_{view_func.__name__}',
        view_func=view_func,
        methods=methods,
    )
