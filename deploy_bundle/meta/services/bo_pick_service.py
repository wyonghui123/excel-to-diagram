# -*- coding: utf-8 -*-
"""
[MODULE] bo_pick_service — BO 选取服务 (V1.2.0)
[DESCRIPTION] 封装按 code / id 精确选取 BO 的业务逻辑, 不应用 read scope 过滤。
              适用场景: 关系表单 source/target BO 选择器的"按编码选" 模式 (V1.2.0 跨域关系 spec)

[设计原则]
  - 不绕过写权限: 调用方仍受 WriteScopeInterceptor 校验 (OR-edit 语义)
  - 仅 bypass 读 scope: 用于在用户 read scope 外"看到" BO 的基本信息
  - 不返回敏感字段: 仅返回 code, name, id, domain_id, version_id, service_module_id, business_object_type, status
  - product_id 必填 (OQ2 决策): 防跨产品误选, 提升查询效率 (走 version_id 子查询)
  - 显式 data_source 注入 (跟 chain_owner_resolver 一致, 便于测试 mock)

[SPEC] .trae/specs/cross-domain-relationship-permission/spec.md
"""
import logging
import os
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


# [V1.2.0] BO Pick Service 公开字段白名单 (不返回 owner_id, created_by 等敏感字段)
# 注: 实际 business_objects 表字段: id, version_id, service_module_id, code, name, description,
#     created_at, updated_at, created_by, updated_by (无 deleted_at/domain_id/business_object_type/status)
_BO_PICK_FIELDS = [
    'id',
    'code',
    'name',
    'description',
    'version_id',
    'service_module_id',
]


def _default_db_path() -> str:
    """[V1.2.0] 默认 DB 路径 (跟 bo_framework 保持一致)"""
    env_db_path = (
        os.environ.get('SQLITE_DB_PATH')
        or os.environ.get('ARCH_DB_PATH')
        or os.environ.get('TEST_DB_PATH')
    )
    if env_db_path:
        return env_db_path
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'architecture.db',
    )


def _default_data_source():
    """[V1.2.0] 延迟获取默认 data_source (避免循环 import)"""
    from meta.core.datasource import get_data_source
    return get_data_source('sqlite', database=_default_db_path())


class BoPickService:
    """[V1.2.0] BO 选取服务 (无状态, 静态方法)"""

    @staticmethod
    def pick_by_code(
        code: str, product_id: int,
        data_source=None,
    ) -> Optional[Dict[str, Any]]:
        """[V1.2.0] 按 code 精确选取 BO (限定 product_id, 不应用 read scope)

        Args:
            code: BO 编码 (如 BO_B_001)
            product_id: 产品 ID (OQ2 决策, 必填)
            data_source: DB 数据源 (可选, 显式注入, 默认 sqlite)

        Returns:
            BO 字典 (含 id, code, name, domain_id, version_id 等基本字段)
            或 None (BO 不存在)
        """
        if not code or not product_id:
            return None

        ds = data_source or _default_data_source()
        fields_str = ', '.join(f'bo.{f}' for f in _BO_PICK_FIELDS)
        sql = f"""
            SELECT {fields_str}
            FROM business_objects bo
            WHERE bo.code = ?
              AND bo.version_id IN (
                  SELECT id FROM versions WHERE product_id = ?
              )
            LIMIT 1
        """
        try:
            cursor = ds.execute(sql, [code, product_id])
            row = cursor.fetchone() if cursor else None
        except Exception as e:
            logger.warning(f'BoPickService.pick_by_code failed: code={code}, product_id={product_id}, err={e}')
            return None

        if not row:
            return None

        # 兼容 dict-like row 或 tuple-like row
        return BoPickService._row_to_dict(row, _BO_PICK_FIELDS)

    @staticmethod
    def pick_by_id(
        bo_id: int, data_source=None,
    ) -> Optional[Dict[str, Any]]:
        """[V1.2.0] 按 id 精确选取 BO (不应用 read scope 过滤)

        Args:
            bo_id: BO ID
            data_source: DB 数据源 (可选, 显式注入, 默认 sqlite)

        Returns:
            BO 字典 或 None
        """
        if not bo_id:
            return None

        ds = data_source or _default_data_source()
        fields_str = ', '.join(f'bo.{f}' for f in _BO_PICK_FIELDS)
        sql = f"""
            SELECT {fields_str}
            FROM business_objects bo
            WHERE bo.id = ?
            LIMIT 1
        """
        try:
            row = ds.execute(sql, [bo_id]).fetchone()
        except Exception as e:
            logger.warning(f'BoPickService.pick_by_id failed: bo_id={bo_id}, err={e}')
            return None

        if not row:
            return None

        return BoPickService._row_to_dict(row, _BO_PICK_FIELDS)

    @staticmethod
    def pick_by_name_fuzzy(
        name: str, product_id: int, limit: int = 20,
        data_source=None,
    ) -> list:
        """[V1.2.0] 按 name 模糊选取 BO (不应用 read scope 过滤, 用于 List 模式搜索增强)

        Args:
            name: 模糊匹配 name
            product_id: 产品 ID (必填)
            limit: 返回数量上限
            data_source: DB 数据源 (可选, 显式注入, 默认 sqlite)

        Returns:
            BO 字典列表
        """
        if not name or not product_id:
            return []

        ds = data_source or _default_data_source()
        fields_str = ', '.join(f'bo.{f}' for f in _BO_PICK_FIELDS)
        sql = f"""
            SELECT {fields_str}
            FROM business_objects bo
            WHERE bo.name LIKE ?
              AND bo.deleted_at IS NULL
              AND bo.version_id IN (
                  SELECT id FROM versions WHERE product_id = ?
              )
            ORDER BY bo.name
            LIMIT ?
        """
        try:
            rows = ds.execute(sql, [f'%{name}%', product_id, limit]).fetchall()
        except Exception as e:
            logger.warning(f'BoPickService.pick_by_name_fuzzy failed: name={name}, err={e}')
            return []

        return [BoPickService._row_to_dict(r, _BO_PICK_FIELDS) for r in rows]

    @staticmethod
    def _row_to_dict(row, fields: list) -> Dict[str, Any]:
        """[V1.2.0] 把 SQL row 转 dict (兼容 dict-like 和 tuple-like row)"""
        # sqlite3.Row 或类似 dict-like
        if hasattr(row, 'keys'):
            return {f: row[f] for f in fields}
        # tuple-like: 按 fields 顺序
        return {fields[i]: row[i] for i in range(len(fields))}
