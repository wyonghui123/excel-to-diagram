# -*- coding: utf-8 -*-
"""
[MODULE] BoYamlCache — BO 元数据缓存 (v1.0.1 轻量版)
[DESCRIPTION] 给 permission_interceptor 提供 parent / chain 关系查询.
              v1.0.1 阶段先 hardcoded (跟 data_permission_service._get_parent_resource 保持一致).
              v1.1 阶段替换为 yaml-driven BoMetadataRegistry.

[USAGE]
    from meta.core.bo_yaml_cache import BoYamlCache
    parent = BoYamlCache.get_parent('sub_domain')
    # → {'object': 'domain', 'field': 'domain_id'}

    chain = BoYamlCache.get_parent_chain('sub_domain')
    # → ['sub_domain', 'domain', 'version', 'product']

[DESIGN]
- 静态方法, 无状态
- v1.0.1: 硬编码 6 BO 的 parent 关系
- v1.1 增量: 加 yaml loader, 把硬编码移到 yaml
"""
from typing import List, Dict, Optional, Any


class BoYamlCache:
    """[v1.0.1] BO 元数据缓存 — 轻量版 (v1.1 升级为 yaml-driven)."""

    # [v1.0.1 硬编码] 6 BO 的 parent 关系 (跟 data_permission_service._get_parent_resource 同步)
    # chain: child → parent 沿 yaml.parent 反向爬, 自下而上
    # 例: sub_domain → domain → version → product
    _PARENT_MAP: Dict[str, Dict[str, str]] = {
        'product':         {'object': None, 'field': None},  # 顶层, 无父
        'version':         {'object': 'product', 'field': 'product_id'},
        'domain':          {'object': 'version', 'field': 'version_id'},
        'sub_domain':      {'object': 'domain',  'field': 'domain_id'},
        'service_module':  {'object': 'sub_domain', 'field': 'sub_domain_id'},
        'business_object': {'object': 'service_module', 'field': 'service_module_id'},
    }

    # 顶层 BO 列表 (chain 起点)
    _TOP_BOS: List[str] = ['product']

    @classmethod
    def get_parent(cls, object_type: str) -> Optional[Dict[str, str]]:
        """[v1.0.1 FR-003] 获取直接父 BO 配置.

        Returns:
            None 表示无父 (顶层 BO)
            {'object': 'xxx', 'field': 'xxx_id'} 表示父 BO 类型和 FK 字段
        """
        cfg = cls._PARENT_MAP.get(object_type)
        if not cfg or not cfg.get('object'):
            return None
        return cfg

    @classmethod
    def get_parent_chain(cls, object_type: str) -> List[str]:
        """[v1.0.1 FR-003b] 沿 parent 反向爬链, 自下而上 (含自身 + 所有祖先到顶层).

        Returns:
            [] 表示无 chain (顶层 BO)
            ['sub_domain', 'domain', 'version', 'product'] 表示 4 级链
        """
        chain = []
        current = object_type
        # 防止循环依赖 (虽然设计上不会)
        visited = set()
        while current and current not in visited:
            visited.add(current)
            chain.append(current)
            parent_cfg = cls._PARENT_MAP.get(current)
            if not parent_cfg or not parent_cfg.get('object'):
                break
            current = parent_cfg['object']
        return chain  # 例: ['sub_domain', 'domain', 'version', 'product']

    @classmethod
    def is_top_bo(cls, object_type: str) -> bool:
        """[v1.0.1] 是否顶层 BO (无父)."""
        return object_type in cls._TOP_BOS

    @classmethod
    def resolve_parent_chain(cls, object_type: str, target_id: int) -> List[Dict[str, Any]]:
        """[v1.0.1 D13 FR-003b.2] 实例级 chain 解析 — 沿 FK 反向爬数据, 返回实际 parent instances.

        Args:
            object_type: 子 BO 类型
            target_id: 子 BO 实例 id

        Returns:
            [
                {'bo': 'domain', 'id': 5, 'field': 'domain_id'},
                {'bo': 'version', 'id': 3, 'field': 'version_id'},
                {'bo': 'product', 'id': 1, 'field': 'product_id'},
            ]
            空列表表示顶层 BO 或解析失败
        """
        try:
            from meta.core.models import get_data_source
            ds = get_data_source()
        except Exception:
            return []

        chain_records = []
        current_type = object_type
        current_id = target_id
        visited = set()
        # 限制深度 (防无限循环, 实际最多 6 级)
        max_depth = 10
        depth = 0
        while current_type and current_id and current_type not in visited and depth < max_depth:
            visited.add(current_type)
            depth += 1
            parent_cfg = cls._PARENT_MAP.get(current_type)
            if not parent_cfg or not parent_cfg.get('object'):
                break  # 顶层 BO

            parent_type = parent_cfg['object']
            fk_field = parent_cfg['field']
            table_name = current_type  # 简化: 假设表名 == bo type

            # 查 FK 字段
            try:
                cursor = ds.execute(
                    f"SELECT {fk_field} FROM {table_name} WHERE id = ?",
                    [current_id]
                )
                row = cursor.fetchone()
                if not row or not row[0]:
                    break
                parent_id = row[0]
            except Exception:
                break

            chain_records.append({
                'bo': parent_type,
                'id': parent_id,
                'field': fk_field,
            })
            current_type = parent_type
            current_id = parent_id

        return chain_records

    @classmethod
    def dump(cls) -> Dict[str, Any]:
        """[v1.0.1 NFR-005] 暴露给 /_diagnostics."""
        return {
            'version': 'v1.0.1-hardcoded',
            'parent_map': dict(cls._PARENT_MAP),
            'top_bos': list(cls._TOP_BOS),
        }
