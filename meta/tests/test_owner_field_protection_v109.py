#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[FIX v1.0.9 2026-06-10] 回归测试: owner 字段保护

测试目的:
  验证 owner_id 字段在创建/编辑时不能被普通用户修改
  - 字段 schema 配置: editable=false, hidden_in_form=true, semantics.immutable=true
  - 创建时由 OwnerAutoPermissionInterceptor 自动注入 current_user
  - 更新时被 _filter_immutable_fields 静默过滤（防止越权改 owner）

注意：v1.1 refactor 后，owner_id 字段已从 version 对象移除（由 product.owner 派生）。
TestOwnerFieldSchema 类已删除，仅保留拦截器逻辑测试。
"""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _make_field(field_id: str, ui: dict = None, semantics: dict = None, name: str = None):
    """模拟 yaml 解析后的 Field 对象（用 SimpleNamespace 支持 getattr 访问）"""
    return SimpleNamespace(
        id=field_id,
        name=name or field_id,
        ui=ui or {},
        semantics=semantics or {},
    )


# ────────────────────────────────────────
# Test 2: 后端 _filter_immutable_fields 在 update 时过滤 owner_id
# ────────────────────────────────────────
class TestUpdateFilterOwner:
    """_filter_immutable_fields 应在 update 时过滤 owner_id"""

    def test_update_filters_owner_id_when_immutable(self):
        """如果 owner_id 字段设了 semantics.immutable=true, update 时应被过滤"""
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor

        # 用 SimpleNamespace 模拟 yaml 解析后的 Field 对象
        # _filter_immutable_fields 用 getattr(f, 'semantics', ...) 取 semantics
        meta_object = SimpleNamespace(
            fields=[
                _make_field(
                    'owner_id',
                    ui={'editable': False, 'hidden_in_form': True},
                    semantics={'immutable': True},
                ),
                _make_field('name', ui={'editable': True}),
            ],
        )

        # 用户尝试传 owner_id + name
        data = {
            'owner_id': 9999,    # 攻击者想改成自己
            'name': '新名称',     # 正常字段
        }

        interceptor = PersistenceInterceptor()
        filtered = interceptor._filter_immutable_fields(meta_object, data)

        # owner_id 应被过滤（用户不能改 owner）
        assert 'owner_id' not in filtered, \
            f"owner_id 应被过滤, 但仍在: {filtered}"
        # name 应保留
        assert filtered.get('name') == '新名称', \
            f"name 应保留, 实际 {filtered.get('name')}"

    def test_update_allows_owner_id_when_not_immutable(self):
        """如果 owner_id 字段没设 immutable, update 时应允许（向后兼容）"""
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor

        meta_object = SimpleNamespace(
            fields=[
                _make_field('owner_id', ui={'editable': True}),
                # 注意: 没有 semantics.immutable
            ],
        )

        data = {'owner_id': 9999}

        interceptor = PersistenceInterceptor()
        filtered = interceptor._filter_immutable_fields(meta_object, data)

        # owner_id 应保留（向后兼容: 旧 schema 没 immutable 标记）
        assert filtered.get('owner_id') == 9999


# ────────────────────────────────────────
# Test 3: OwnerAutoPermissionInterceptor 在 create 时强制注入
# ────────────────────────────────────────
class TestOwnerAutoInject:
    """OwnerAutoPermissionInterceptor 应在 create 时强制覆盖 owner_id"""

    def test_create_auto_injects_current_user_as_owner(self):
        """创建时即使前端传了 owner_id, 也会被覆盖为 current_user"""
        from meta.core.interceptors.owner_permission_interceptor import (
            OwnerAutoPermissionInterceptor,
        )
        from meta.core.action_context import ActionContext

        interceptor = OwnerAutoPermissionInterceptor()

        # 模拟 create context
        ctx = MagicMock(spec=ActionContext)
        ctx.is_create_action = True
        ctx.is_update_action = False
        ctx.user_id = 1456  # TESET68
        ctx.params = {'owner_id': 9999, 'name': 'Test Version'}  # 攻击者传了 owner_id=9999
        ctx.meta_object = MagicMock()
        ctx.meta_object.authorization = {
            'auto_owner': True,
            'auto_permission': 'admin',
        }

        interceptor.before_action(ctx)

        # owner_id 应被覆盖为 current_user (1456)
        assert ctx.params.get('owner_id') == 1456, \
            f"owner_id 应被自动注入为 current_user, 实际 {ctx.params.get('owner_id')}"

    def test_create_does_not_inject_when_auto_owner_false(self):
        """如果 auto_owner=false, 不注入（向后兼容）"""
        from meta.core.interceptors.owner_permission_interceptor import (
            OwnerAutoPermissionInterceptor,
        )
        from meta.core.action_context import ActionContext

        interceptor = OwnerAutoPermissionInterceptor()

        ctx = MagicMock(spec=ActionContext)
        ctx.is_create_action = True
        ctx.user_id = 1456
        ctx.params = {'name': 'Test Version'}
        ctx.meta_object = MagicMock()
        ctx.meta_object.authorization = {
            'auto_owner': False,
        }

        interceptor.before_action(ctx)

        # 不应注入 owner_id
        assert 'owner_id' not in ctx.params

    def test_update_does_not_inject_owner(self):
        """update 时不应注入 owner_id（让 _filter_immutable_fields 处理）"""
        from meta.core.interceptors.owner_permission_interceptor import (
            OwnerAutoPermissionInterceptor,
        )
        from meta.core.action_context import ActionContext

        interceptor = OwnerAutoPermissionInterceptor()

        ctx = MagicMock(spec=ActionContext)
        ctx.is_create_action = False
        ctx.is_update_action = True
        ctx.user_id = 1456
        ctx.params = {'owner_id': 9999}  # 攻击者尝试在 update 时改 owner
        ctx.meta_object = MagicMock()
        ctx.meta_object.authorization = {
            'auto_owner': True,
        }

        interceptor.before_action(ctx)

        # update 时不应注入（early return）
        assert ctx.params.get('owner_id') == 9999, \
            f"update 时 owner_id 不应被注入, 实际 {ctx.params.get('owner_id')}"


# ────────────────────────────────────────
# Test 4: 端到端场景 - TESET68 越权改 owner
# ────────────────────────────────────────
class TestTeset68CannotChangeOwner:
    """TESET68 不能通过 update API 把别人 draft 的 owner 改成自己"""

    def test_update_strips_owner_id_to_prevent_ownership_theft(self):
        """update API 调用时即使传了 owner_id, 也应被 _filter_immutable_fields 过滤"""
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor

        # 模拟 version meta_object (用 SimpleNamespace 避免 MagicMock 坑)
        meta_object = SimpleNamespace(
            fields=[
                _make_field(
                    'owner_id',
                    ui={'editable': False, 'hidden_in_form': True},
                    semantics={'immutable': True},
                ),
                _make_field('name'),
            ],
        )

        # TESET68 攻击: 把别人 version 的 owner 改成自己
        attack_data = {
            'owner_id': 1456,    # TESET68 想偷走 version
            'name': 'new name',  # 顺便改个名
        }

        interceptor = PersistenceInterceptor()
        filtered = interceptor._filter_immutable_fields(meta_object, attack_data)

        # owner_id 应被过滤（保护机制）
        assert 'owner_id' not in filtered, \
            f"[安全] owner_id 必须被过滤, 否则用户能偷走别人的资源. filtered={filtered}"
        # name 应保留
        assert filtered.get('name') == 'new name'