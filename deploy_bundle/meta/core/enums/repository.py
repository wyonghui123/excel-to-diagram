# -*- coding: utf-8 -*-
"""
枚举数据仓库（Repository）

统一的数据访问层，封装所有 enum_types / enum_values 表的 CRUD 操作。
提供类型安全的查询方法，支持维度过滤、分页、排序等高级功能。

设计原则：
- 单一职责：只负责数据访问，不包含业务逻辑
- 类型安全：使用 DTO 进行数据传递
- 性能优化：支持批量查询和预加载
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .dto import EnumTypeDTO, EnumValueDTO

logger = logging.getLogger(__name__)


class EnumNotFoundError(Exception):
    """枚举类型不存在错误"""
    pass


class EnumValueNotFoundError(Exception):
    """枚举值不存在错误"""
    pass


class EnumRepository:
    """
    枚举数据仓库
    
    封装对 enum_types 和 enum_values 表的所有数据库操作，
    提供类型安全的数据访问接口。
    
    使用方式：
        repo = EnumRepository(data_source)
        values = await repo.find_active_values('order_status')
        type_info = await repo.find_type_by_id('order_status')
    """
    
    def __init__(self, data_source=None):
        """
        初始化 Repository
        
        Args:
            data_source: 数据库连接对象（可选，延迟初始化）
        """
        self._ds = data_source
        self._initialized = False
    
    def _get_ds(self):
        """延迟获取数据源"""
        if not self._initialized or not self._ds:
            try:
                from meta.api.manage_api import _get_data_source
                self._ds = _get_data_source()
                self._initialized = True
            except Exception as e:
                logger.error(f"无法初始化数据源: {e}")
                raise
        return self._ds
    
    # ══════════════════════════════════════════════════════════
    # 枚举类型 CRUD
    # ══════════════════════════════════════════════════════════
    
    async def find_type_by_id(self, enum_type_id: str) -> Optional[EnumTypeDTO]:
        """
        根据ID查找枚举类型
        
        Args:
            enum_type_id: 类型ID（如 'order_status'）
            
        Returns:
            EnumTypeDTO 对象，如果不存在返回 None
        """
        ds = self._get_ds()
        
        try:
            ds.execute("""
                SELECT id, name, category, mutability, description,
                       dimension_schema, is_active
                FROM enum_types 
                WHERE id = ?
            """, (enum_type_id,))
            
            row = ds.fetchone()
            
            if not row:
                logger.warning(f"枚举类型不存在: {enum_type_id}")
                return None
            
            # 统计值数量
            value_count = await self._count_values(enum_type_id)
            
            # 解析维度Schema
            dimension_schema = None
            if row[5]:  # dimension_schema
                try:
                    dimension_schema = json.loads(row[5])
                except (json.JSONDecodeError, TypeError):
                    dimension_schema = None
            
            return EnumTypeDTO(
                id=row[0],
                name=row[1],
                category=row[2],
                mutability=row[3],
                description=row[4] or "",
                dimension_schema=dimension_schema,
                value_count=value_count,
                is_active=bool(row[6]),
            )
            
        except Exception as e:
            logger.error(f"查询枚举类型失败 [{enum_type_id}]: {e}", exc_info=True)
            raise
    
    async def find_all_types(
        self,
        category: Optional[str] = None,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0
    ) -> List[EnumTypeDTO]:
        """
        查找所有枚举类型
        
        Args:
            category: 可选的分类过滤
            include_inactive: 是否包含停用的类型
            limit: 返回数量限制
            offset: 偏移量
            
        Returns:
            EnumTypeDTO 列表
        """
        ds = self._get_ds()
        
        conditions = []
        params = []
        
        if category:
            conditions.append("category = ?")
            params.append(category)
            
        if not include_inactive:
            conditions.append("is_active = 1")
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        try:
            ds.execute(f"""
                SELECT id, name, category, mutability, description,
                       dimension_schema, is_active
                FROM enum_types 
                WHERE {where_clause}
                ORDER BY name ASC
                LIMIT ? OFFSET ?
            """, params + [limit, offset])
            
            rows = ds.fetchall()
            results = []
            
            for row in rows:
                dimension_schema = None
                if row[5]:
                    try:
                        dimension_schema = json.loads(row[5])
                    except (json.JSONDecodeError, TypeError):
                        dimension_schema = None
                
                results.append(EnumTypeDTO(
                    id=row[0],
                    name=row[1],
                    category=row[2],
                    mutability=row[3],
                    description=row[4] or "",
                    dimension_schema=dimension_schema,
                    value_count=await self._count_values(row[0]),
                    is_active=bool(row[6]),
                ))
            
            return results
            
        except Exception as e:
            logger.error(f"查询枚举类型列表失败: {e}", exc_info=True)
            raise
    
    async def insert_type(self, data: Dict[str, Any]) -> str:
        """
        插入新的枚举类型
        
        Args:
            data: 类型数据字典
            
        Returns:
            新插入的类型ID
        """
        ds = self._get_ds()
        
        now = datetime.now().isoformat()
        
        try:
            ds.execute("""
                INSERT INTO enum_types (
                    id, name, category, mutability, 
                    description, dimension_schema,
                    created_at, updated_at, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (
                data['id'],
                data.get('name', ''),
                data.get('category', 'business'),
                data.get('mutability', 'extensible'),
                data.get('description', ''),
                json.dumps(data.get('dimension_schema'), ensure_ascii=False) if data.get('dimension_schema') else None,
                now,
                now,
            ))
            
            logger.info(f"[OK] 创建枚举类型成功: {data['id']}")
            return data['id']
            
        except Exception as e:
            logger.error(f"创建枚举类型失败: {e}", exc_info=True)
            raise
    
    async def update_type(self, enum_type_id: str, data: Dict[str, Any]) -> bool:
        """
        更新枚举类型
        
        Args:
            enum_type_id: 类型ID
            data: 要更新的字段
            
        Returns:
            是否更新成功
        """
        ds = self._get_ds()
        
        now = datetime.now().isoformat()
        
        # 构建动态UPDATE语句
        set_clauses = []
        params = []
        
        updatable_fields = ['name', 'category', 'mutability', 'description', 'dimension_schema', 'is_active']
        
        for field in updatable_fields:
            if field in data:
                if field == 'dimension_schema':
                    set_clauses.append(f"{field} = ?")
                    params.append(json.dumps(data[field], ensure_ascii=False))
                elif field == 'is_active':
                    set_clauses.append(f"{field} = ?")
                    params.append(1 if data[field] else 0)
                else:
                    set_clauses.append(f"{field} = ?")
                    params.append(data[field])
        
        if not set_clauses:
            logger.warning(f"没有需要更新的字段: {enum_type_id}")
            return False
        
        set_clauses.append("updated_at = ?")
        params.append(now)
        params.append(enum_type_id)
        
        try:
            ds.execute(f"""
                UPDATE enum_types 
                SET {', '.join(set_clauses)}
                WHERE id = ?
            """, tuple(params))
            
            logger.info(f"[OK] 更新枚举类型成功: {enum_type_id}")
            return True
            
        except Exception as e:
            logger.error(f"更新枚举类型失败 [{enum_type_id}]: {e}", exc_info=True)
            raise
    
    async def delete_type(self, enum_type_id: str, cascade: bool = True) -> bool:
        """
        删除枚举类型
        
        Args:
            enum_type_id: 类型ID
            cascade: 是否级联删除所有值
            
        Returns:
            是否删除成功
        """
        ds = self._get_ds()
        
        try:
            if cascade:
                # 先删除所有值
                ds.execute("DELETE FROM enum_values WHERE enum_type_id = ?", (enum_type_id,))
                logger.info(f"  级联删除了类型 [{enum_type_id}] 的所有枚举值")
            
            # 删除类型本身
            ds.execute("DELETE FROM enum_types WHERE id = ?", (enum_type_id,))
            
            logger.info(f"[OK] 删除枚举类型成功: {enum_type_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除枚举类型失败 [{enum_type_id}]: {e}", exc_info=True)
            raise
    
    # ══════════════════════════════════════════════════════════
    # 枚举值 CRUD
    # ══════════════════════════════════════════════════════════
    
    async def find_values(
        self,
        enum_type_id: str,
        include_inactive: bool = False,
        **filters
    ) -> List[EnumValueDTO]:
        """
        查找枚举类型的所有值
        
        Args:
            enum_type_id: 类型ID
            include_inactive: 是否包含停用的值
            **filters: 额外过滤条件
            
        Returns:
            EnumValueDTO 列表（按sort_order排序）
        """
        ds = self._get_ds()
        
        conditions = ["enum_type_id = ?"]
        params = [enum_type_id]
        
        if not include_inactive:
            conditions.append("is_active = 1")
        
        # 维度过滤
        if filters:
            for key, value in filters.items():
                if key == 'parent_code':
                    if value is None:
                        conditions.append("(parent_code IS NULL OR parent_code = '')")
                    else:
                        conditions.append("parent_code = ?")
                        params.append(value)
        
        where_clause = " AND ".join(conditions)
        
        try:
            ds.execute(f"""
                SELECT id, enum_type_id, code, name, name_en,
                       dimensions, sort_order, is_active, is_system,
                       parent_code, metadata, created_at, updated_at
                FROM enum_values 
                WHERE {where_clause}
                ORDER BY sort_order ASC, code ASC
            """, tuple(params))
            
            rows = ds.fetchall()
            results = []
            
            for row in rows:
                dimensions = None
                if row[5]:
                    try:
                        dimensions = json.loads(row[5]) if isinstance(row[5], str) else row[5]
                    except (json.JSONDecodeError, TypeError):
                        dimensions = {}
                
                metadata = None
                if row[11]:
                    try:
                        metadata = json.loads(row[11]) if isinstance(row[11], str) else row[11]
                    except (json.JSONDecodeError, TypeError):
                        metadata = {}
                
                results.append(EnumValueDTO(
                    id=row[0],
                    enum_type_id=row[1],
                    code=row[2],
                    name=row[3] or "",
                    name_en=row[4],
                    dimensions=dimensions,
                    sort_order=row[6] or 0,
                    is_active=bool(row[7]),
                    is_system=bool(row[8]),
                    parent_code=row[9] or None,
                    metadata=metadata,
                ))
            
            return results
            
        except Exception as e:
            logger.error(f"查询枚举值失败 [{enum_type_id}]: {e}", exc_info=True)
            raise
    
    async def find_active_values(self, enum_type_id: str) -> List[EnumValueDTO]:
        """
        查找活跃的枚举值（快捷方法）
        
        Args:
            enum_type_id: 类型ID
            
        Returns:
            活跃的 EnumValueDTO 列表
        """
        return await self.find_values(enum_type_id, include_inactive=False)
    
    async def find_value_by_code(
        self,
        enum_type_id: str,
        code: str
    ) -> Optional[EnumValueDTO]:
        """
        根据编码查找单个枚举值
        
        Args:
            enum_type_id: 类型ID
            code: 枚举值编码
            
        Returns:
            EnumValueDTO 对象，如果不存在返回 None
        """
        ds = self._get_ds()
        
        try:
            ds.execute("""
                SELECT id, enum_type_id, code, name, name_en,
                       dimensions, sort_order, is_active, is_system,
                       parent_code, metadata, created_at, updated_at
                FROM enum_values 
                WHERE enum_type_id = ? AND code = ?
                LIMIT 1
            """, (enum_type_id, code))
            
            row = ds.fetchone()
            
            if not row:
                return None
            
            dimensions = None
            if row[5]:
                try:
                    dimensions = json.loads(row[5]) if isinstance(row[5], str) else row[5]
                except (json.JSONDecodeError, TypeError):
                    dimensions = {}
            
            metadata = None
            if row[11]:
                try:
                    metadata = json.loads(row[11]) if isinstance(row[11], str) else row[11]
                except (json.JSONDecodeError, TypeError):
                    metadata = {}
            
            return EnumValueDTO(
                id=row[0],
                enum_type_id=row[1],
                code=row[2],
                name=row[3] or "",
                name_en=row[4],
                dimensions=dimensions,
                sort_order=row[6] or 0,
                is_active=bool(row[7]),
                is_system=bool(row[8]),
                parent_code=row[9] or None,
                metadata=metadata,
            )
            
        except Exception as e:
            logger.error(f"查询枚举值失败 [{enum_type_id}/{code}]: {e}", exc_info=True)
            raise
    
    async def insert_value(self, enum_type_id: str, data: Dict[str, Any]) -> int:
        """
        插入新的枚举值
        
        Args:
            enum_type_id: 所属类型ID
            data: 值数据字典
            
        Returns:
            新插入值的ID（主键）
        """
        ds = self._get_ds()
        
        now = datetime.now().isoformat()
        
        try:
            ds.execute("""
                INSERT INTO enum_values (
                    enum_type_id, code, name, name_en,
                    dimensions, sort_order, is_active, is_system,
                    parent_code, metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                enum_type_id,
                data['code'],
                data.get('name', ''),
                data.get('name_en'),
                json.dumps(data.get('dimensions'), ensure_ascii=False) if data.get('dimensions') else None,
                data.get('sort_order', 0),
                1 if data.get('is_active', True) else 0,
                1 if data.get('is_system', False) else 0,
                data.get('parent_code'),
                json.dumps(data.get('metadata'), ensure_ascii=False) if data.get('metadata') else None,
                now,
                now,
            ))
            
            # 获取新插入的ID
            ds.execute("SELECT last_insert_rowid()")
            new_id = ds.fetchone()[0]
            
            logger.info(f"[OK] 创建枚举值成功: {enum_type_id}/{data['code']} (ID={new_id})")
            return new_id
            
        except Exception as e:
            logger.error(f"创建枚举值失败: {e}", exc_info=True)
            raise
    
    async def update_value(self, value_id: int, data: Dict[str, Any]) -> bool:
        """
        更新枚举值
        
        Args:
            value_id: 值的主键ID
            data: 要更新的字段
            
        Returns:
            是否更新成功
        """
        ds = self._get_ds()
        
        now = datetime.now().isoformat()
        
        set_clauses = []
        params = []
        
        updatable_fields = ['code', 'name', 'name_en', 'dimensions', 'sort_order',
                           'is_active', 'parent_code', 'metadata']
        
        for field in updatable_fields:
            if field in data:
                if field in ('dimensions', 'metadata'):
                    set_clauses.append(f"{field} = ?")
                    params.append(json.dumps(data[field], ensure_ascii=False))
                elif field in ('is_active', 'is_system'):
                    set_clauses.append(f"{field} = ?")
                    params.append(1 if data[field] else 0)
                else:
                    set_clauses.append(f"{field} = ?")
                    params.append(data[field])
        
        if not set_clauses:
            logger.warning(f"没有需要更新的字段: value_id={value_id}")
            return False
        
        set_clauses.append("updated_at = ?")
        params.append(now)
        params.append(value_id)
        
        try:
            ds.execute(f"""
                UPDATE enum_values 
                SET {', '.join(set_clauses)}
                WHERE id = ?
            """, tuple(params))
            
            logger.info(f"[OK] 更新枚举值成功: value_id={value_id}")
            return True
            
        except Exception as e:
            logger.error(f"更新枚举值失败 [value_id={value_id}]: {e}", exc_info=True)
            raise
    
    async def delete_value(self, value_id: int) -> bool:
        """
        删除枚举值
        
        Args:
            value_id: 值的主键ID
            
        Returns:
            是否删除成功
        """
        ds = self._get_ds()
        
        try:
            ds.execute("DELETE FROM enum_values WHERE id = ?", (value_id,))
            logger.info(f"[OK] 删除枚举值成功: value_id={value_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除枚举值失败 [value_id={value_id}]: {e}", exc_info=True)
            raise
    
    async def batch_update_sort_order(
        self,
        enum_type_id: str,
        items: List[Dict[str, Any]]
    ) -> bool:
        """
        批量更新排序
        
        Args:
            enum_type_id: 类型ID
            items: 排序项列表 [{'id': 1, 'sort_order': 1}, ...]
            
        Returns:
            是否全部更新成功
        """
        ds = self._get_ds()
        
        success_count = 0
        
        try:
            for item in items:
                ds.execute("""
                    UPDATE enum_values 
                    set sort_order = ?, updated_at = ?
                    WHERE id = ? AND enum_type_id = ?
                """, (item['sort_order'], datetime.now().isoformat(), item['id'], enum_type_id))
                success_count += 1
            
            logger.info(f"[OK] 批量更新排序成功: {success_count}/{len(items)} 条")
            return True
            
        except Exception as e:
            logger.error(f"批量更新排序失败: {e}", exc_info=True)
            raise
    
    async def toggle_value_active(self, value_id: int) -> Tuple[bool, bool]:
        """
        切换枚举值启用/停用状态
        
        Args:
            value_id: 值的主键ID
            
        Returns:
            (是否操作成功, 新的状态)
        """
        ds = self._get_ds()
        
        try:
            # 先查询当前状态
            ds.execute("SELECT is_active FROM enum_values WHERE id = ?", (value_id,))
            row = ds.fetchone()
            
            if not row:
                raise EnumValueNotFoundError(f"枚举值不存在: value_id={value_id}")
            
            current_status = bool(row[0])
            new_status = not current_status
            
            # 更新状态
            ds.execute("""
                UPDATE enum_values 
                SET is_active = ?, updated_at = ?
                WHERE id = ?
            """, (1 if new_status else 0, datetime.now().isoformat(), value_id))
            
            action = "启用" if new_status else "停用"
            logger.info(f"[OK] {action}枚举值成功: value_id={value_id}")
            
            return (True, new_status)
            
        except EnumValueNotFoundError:
            raise
        except Exception as e:
            logger.error(f"切换枚举值状态失败 [value_id={value_id}]: {e}", exc_info=True)
            raise
    
    # ══════════════════════════════════════════════════════════
    # 辅助方法
    # ══════════════════════════════════════════════════════════
    
    async def _count_values(self, enum_type_id: str) -> int:
        """统计指定类型的枚举值数量"""
        ds = self._get_ds()
        
        try:
            ds.execute("""
                SELECT COUNT(*) FROM enum_values WHERE enum_type_id = ?
            """, (enum_type_id,))
            
            result = ds.fetchone()
            return result[0] if result else 0
            
        except Exception as e:
            logger.warning(f"统计枚举值数量失败 [{enum_type_id}]: {e}")
            return 0
    
    async def exists_type(self, enum_type_id: str) -> bool:
        """检查枚举类型是否存在"""
        type_info = await self.find_type_by_id(enum_type_id)
        return type_info is not None
    
    async def exists_value(self, enum_type_id: str, code: str) -> bool:
        """检查枚举值是否存在"""
        value = await self.find_value_by_code(enum_type_id, code)
        return value is not None
    
    async def get_valid_codes(self, enum_type_id: str) -> List[str]:
        """
        获取所有有效的枚举编码列表
        
        用于高速校验场景（如 HashSet 查找）。
        目标性能：< 1ms
        """
        values = await self.find_active_values(enum_type_id)
        return [v.code for v in values]
