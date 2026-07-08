# -*- coding: utf-8 -*-
"""
聚合刷新处理器（Aggregate Refresh Handler）

核心职责：
1. 监听数据变更事件
2. 判断哪些聚合受影响
3. 触发增量刷新

设计参考：
- SAP HANA 的 Auto-Refresh Materialized View
- Salesforce 的 Summary Field Auto-Calculation

使用示例：
    from meta.core.aggregate_refresh_handler import AggregateRefreshHandler
    
    handler = AggregateRefreshHandler(aggregate_manager)
    
    # 在变更通知中调用
    handler.on_data_changed('relationship', record_id=1, event_type='updated')
"""

from typing import Optional, List, Set
import logging

logger = logging.getLogger(__name__)


class AggregateRefreshHandler:
    """聚合刷新处理器
    
    监听数据变更事件，自动触发受影响聚合的刷新。
    """
    
    def __init__(self, aggregate_manager):
        self.aggregate_manager = aggregate_manager
    
    def on_data_changed(
        self,
        object_type: str,
        record_id: Optional[int] = None,
        event_type: str = "updated",
        changed_fields: Optional[dict] = None
    ) -> int:
        """处理数据变更事件
        
        Args:
            object_type: 变更的对象类型
            record_id: 变更记录ID
            event_type: 事件类型 (created/updated/deleted)
            changed_fields: 变更的字段
            
        Returns:
            刷新的聚合数量
        """
        if event_type not in ("created", "updated", "deleted"):
            return 0
        
        refreshed = self.aggregate_manager.refresh_on_change(
            object_type, record_id, event_type
        )
        
        if refreshed > 0:
            logger.info(
                "[AggregateRefreshHandler] %s.%s %s → 刷新 %d 个聚合",
                object_type, record_id, event_type, refreshed
            )
        
        return refreshed
    
    def on_batch_changed(
        self,
        changes: List[dict]
    ) -> int:
        """处理批量变更事件
        
        Args:
            changes: 变更列表，每个元素包含 object_type, record_id, event_type
            
        Returns:
            刷新的聚合数量
        """
        affected_objects: Set[str] = set()
        
        for change in changes:
            object_type = change.get("object_type", "")
            if object_type:
                affected_objects.add(object_type)
        
        total_refreshed = 0
        for object_type in affected_objects:
            total_refreshed += self.aggregate_manager.refresh_on_change(
                object_type, None, "batch_updated"
            )
        
        return total_refreshed
