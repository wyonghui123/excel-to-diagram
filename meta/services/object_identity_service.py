# -*- coding: utf-8 -*-
"""
统一对象标识服务

整合 Key 和 Hierarchy 信息，提供完整的对象身份识别能力
"""

from typing import Dict, List, Tuple, Optional, Any
import logging

from meta.services.business_key_service import BusinessKeyService
from meta.services.hierarchy_path_service import HierarchyPathService
from meta.core.yaml_loader import registry

logger = logging.getLogger(__name__)


class ObjectIdentityService:
    """
    统一对象标识服务
    
    整合 BusinessKey 和 HierarchyPath 信息，提供完整的对象身份识别
    """
    
    def __init__(self, data_source):
        """
        初始化对象标识服务
        
        Args:
            data_source: 数据源对象
        """
        self.data_source = data_source
        self.business_key_service = BusinessKeyService(data_source)
        self.hierarchy_path_service = HierarchyPathService(data_source)
        self._cache = {}
    
    def get_identity(
        self,
        object_type: str,
        object_id: int,
        format: str = 'full',
        include_technical: bool = False
    ) -> Dict[str, Any]:
        """
        获取对象的完整身份标识
        
        Args:
            object_type: 对象类型
            object_id: 对象 ID
            format: 输出格式
                - 'full': 完整标识（含层级路径）
                - 'short': 简短标识（仅业务键）
                - 'minimal': 最小标识（仅编码）
                - 'technical': 技术标识（ID + 类型）
                - 'detailed': 详细标识（所有信息）
            include_technical: 是否包含技术信息
        
        Returns:
            {
                'formatted': 'ERP产品 → V5 → 供应链云 [SUPPLY_CHAIN]',
                'technical': {'id': 123, 'object_type': 'domain'},
                'semantic': {'business_key': 'ERP|V5|SUPPLY_CHAIN'},
                'display': {'name': '供应链云', 'code': 'SUPPLY_CHAIN'},
                'hierarchical': {'full_path': 'ERP产品 → V5 → 供应链云', 'depth': 3}
            }
        """
        if not object_type or not object_id:
            return {
                'formatted': '',
                'technical': {},
                'semantic': {},
                'display': {},
                'hierarchical': {}
            }
        
        cache_key = f"{object_type}:{object_id}:{format}:{include_technical}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            result = {
                'formatted': '',
                'technical': {},
                'semantic': {},
                'display': {},
                'hierarchical': {}
            }
            
            if include_technical or format == 'technical':
                result['technical'] = {
                    'id': object_id,
                    'object_type': object_type
                }
            
            business_key = self.business_key_service.id_to_business_key(
                object_type, object_id, format='short'
            )

            result['semantic'] = {
                'business_key': business_key
            }

            meta_obj = registry.get(object_type)
            display_name = ''
            display_code = ''
            extra_display_columns: List[str] = []
            if meta_obj:
                table_name = meta_obj.table_name
                # [FIX 2026-06-11] 增强 display 字段: 按 schema 优先级提取
                #   1) schema.display_name_field (e.g. relationship.relation_desc)
                #   2) semantics.display_name=true 字段
                #   3) 字段 id 含 'name' (e.g. annotation.content, business_object.name)
                #   4) 字段 id 含 'desc' / 'description' (fallback)
                # 只 SELECT 表中真实存在的列, 避免 'no such column' 错误
                valid_columns = {f.db_column or f.id for f in (meta_obj.fields or [])}
                display_field, code_field, extra_cols = self._resolve_display_fields(meta_obj)
                candidate_cols = [display_field, code_field] + extra_cols
                # 仅加入 schema 中真实存在的列
                select_cols = [c for c in candidate_cols if c and c in valid_columns]
                if not select_cols:
                    # fallback: SELECT id, 用 _fallback_display_value 二次尝试
                    select_cols = ['id']
                query = f"SELECT {', '.join(select_cols)} FROM {table_name} WHERE id = ?"
                try:
                    cursor = self.data_source.execute(query, (int(object_id),))
                    row = cursor.fetchone()
                except Exception as col_err:
                    logger.warning(f"Display query failed for {object_type}:{object_id}: {col_err}; falling back to SELECT id")
                    cursor = self.data_source.execute(f"SELECT id FROM {table_name} WHERE id = ?", (int(object_id),))
                    row = cursor.fetchone()

                if row:
                    columns = [desc[0] for desc in cursor.description]
                    record = dict(zip(columns, row))

                    display_name = str(record.get(display_field) or '').strip() if display_field and display_field in record else ''
                    display_code = str(record.get(code_field) or '').strip() if code_field and code_field in record else ''

                    result['display'] = {
                        'name': display_name,
                        'code': display_code,
                        'name_field': display_field,
                        'code_field': code_field,
                    }

            hierarchy_path = self.hierarchy_path_service.get_full_path(
                object_type, object_id, path_type='full_path'
            )
            
            result['hierarchical'] = {
                'full_path': hierarchy_path.get('full', ''),
                'short_path': hierarchy_path.get('short', ''),
                'depth': hierarchy_path.get('depth', 0),
                'segments': hierarchy_path.get('segments', [])
            }
            
            result['formatted'] = self._format_identity(result, format)
            
            self._cache[cache_key] = result
            return result
            
        except Exception as e:
            logger.error(f"Failed to get identity for {object_type}:{object_id}: {e}")
            import traceback
            traceback.print_exc()
            return {
                'formatted': f"{object_type}:{object_id}",
                'technical': {'id': object_id, 'object_type': object_type},
                'semantic': {},
                'display': {},
                'hierarchical': {}
            }
    
    def _resolve_display_fields(self, meta_obj) -> Tuple[str, str, List[str]]:
        """[FIX 2026-06-11] 解析对象的主显示字段 / 主编码字段, 用于审计日志展示.

        优先级:
          1) schema.display_name_field (e.g. relationship.relation_desc)
          2) semantics.display_name=true 的字段
          3) 字段 id 含 'name' 且 type 非 enum (e.g. annotation 无 display_name 时,
             不会匹配到 'name', 但 'content' 是 fallback - 这里 'name' 不命中, 走 desc)
          4) 字段 id 含 'desc' / 'description' / 'content'

        Returns:
            (name_field, code_field, extra_columns)
            - name_field: db_column 名 (如 'relation_desc', 'name', 'content')
            - code_field: db_column 名 (如 'code', 'source_code'), 无则空
            - extra_columns: 其他需要 SELECT 的列 (暂时保留扩展位)
        """
        # 1) schema.display_name_field
        display_attr = getattr(meta_obj, 'display_name_field', None) or ''
        name_field = display_attr.strip() if isinstance(display_attr, str) else ''

        # 2) semantics.display_name=true
        if not name_field:
            for f in meta_obj.fields or []:
                if f.semantics and getattr(f.semantics, 'display_name', False):
                    name_field = f.db_column or f.id
                    break

        # 3) 字段 id 含 'name'
        if not name_field:
            for f in meta_obj.fields or []:
                fid = (f.id or '').lower()
                if 'name' in fid and 'enum' not in fid:
                    name_field = f.db_column or f.id
                    break

        # 4) desc / description / content / text
        if not name_field:
            for f in meta_obj.fields or []:
                fid = (f.id or '').lower()
                if any(k in fid for k in ('description', 'desc', 'content')):
                    name_field = f.db_column or f.id
                    break

        # code 字段: 优先 semantics.data_category=code, 退到 'code'
        code_field = ''
        for f in meta_obj.fields or []:
            if f.semantics and getattr(f.semantics, 'data_category', '') == 'code':
                code_field = f.db_column or f.id
                break
        if not code_field:
            for f in meta_obj.fields or []:
                if (f.id or '').lower() == 'code':
                    code_field = f.db_column or f.id
                    break

        return name_field, code_field, []

    def _format_identity(self, identity: Dict[str, Any], format: str) -> str:
        """
        格式化对象标识
        
        Args:
            identity: 身份信息字典
            format: 输出格式
        
        Returns:
            格式化的标识字符串
        """
        if format == 'technical':
            tech = identity.get('technical', {})
            return f"{tech.get('object_type', '')}:{tech.get('id', '')}"
        
        elif format == 'minimal':
            semantic = identity.get('semantic', {})
            return semantic.get('business_key', '')
        
        elif format == 'short':
            display = identity.get('display', {})
            name = display.get('name', '')
            code = display.get('code', '')
            
            if name and code:
                return f"{name} [{code}]"
            elif name:
                return name
            elif code:
                return code
            else:
                return identity.get('semantic', {}).get('business_key', '')
        
        elif format == 'detailed':
            hierarchical = identity.get('hierarchical', {})
            display = identity.get('display', {})
            
            parts = []
            
            full_path = hierarchical.get('full_path', '')
            if full_path:
                parts.append(full_path)
            
            code = display.get('code', '')
            if code:
                parts.append(f"[{code}]")
            
            return ' '.join(parts) if parts else identity.get('semantic', {}).get('business_key', '')
        
        else:
            hierarchical = identity.get('hierarchical', {})
            display = identity.get('display', {})
            
            full_path = hierarchical.get('full_path', '')
            code = display.get('code', '')
            
            if full_path and code:
                return f"{full_path} [{code}]"
            elif full_path:
                return full_path
            elif code:
                return code
            else:
                return identity.get('semantic', {}).get('business_key', '')
    
    def batch_get_identities(
        self,
        requests: List[Tuple[str, int]],
        format: str = 'full',
        include_technical: bool = False
    ) -> Dict[Tuple[str, int], Dict[str, Any]]:
        """
        批量获取对象标识
        
        Args:
            requests: 对象列表 [(object_type, object_id), ...]
            format: 输出格式
            include_technical: 是否包含技术信息
        
        Returns:
            映射字典，键为 (object_type, object_id)，值为身份信息
        """
        results = {}
        
        for object_type, object_id in requests:
            result = self.get_identity(object_type, object_id, format, include_technical)
            results[(object_type, object_id)] = result
        
        return results
    
    def get_formatted_identity(
        self,
        object_type: str,
        object_id: int,
        format: str = 'full'
    ) -> str:
        """
        获取格式化的对象标识字符串
        
        Args:
            object_type: 对象类型
            object_id: 对象 ID
            format: 输出格式
        
        Returns:
            格式化的标识字符串
        """
        identity = self.get_identity(object_type, object_id, format)
        return identity.get('formatted', '')
    
    def clear_cache(self):
        """清空所有缓存"""
        self._cache.clear()
        self.business_key_service.clear_cache()
        self.hierarchy_path_service.clear_cache()
        logger.info("ObjectIdentityService cache cleared")
