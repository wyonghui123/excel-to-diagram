"""
对象视角审计日志验证器

扩展 AuditLogVerifier，增加对象视角的三层日志完整性验证：
- Layer 1: 对象自身日志
- Layer 2: 关联日志（source 侧 + target 侧反向 + relationship 参与方）
- Layer 3: 子对象日志（级联删除 + 模型配置）

使用示例:
    from test_helpers.object_audit_verifier import ObjectAuditLogVerifier

    verifier = ObjectAuditLogVerifier(data_source)

    result = verifier.verify_object_perspective('users', 123)
    assert result['valid'], result['errors']
    # result['layers'] = { own_logs, association_logs, children_logs }
"""
import json
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field

from test_helpers.audit_log_verifier import AuditLogVerifier, VerificationResult


@dataclass
class ObjectPerspectiveResult:
    """对象视角验证结果"""
    valid: bool
    object_type: str
    object_id: Any
    layers: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'valid': self.valid,
            'object_type': self.object_type,
            'object_id': self.object_id,
            'layers': self.layers,
            'errors': self.errors,
            'warnings': self.warnings
        }


class ObjectAuditLogVerifier(AuditLogVerifier):
    """
    对象视角审计日志验证器
    
    三层日志模型：
    - Layer 1: 自身日志 (own logs)
    - Layer 2: 关联日志 (association logs)
    - Layer 3: 子对象日志 (children logs)
    """
    
    AUDIT_TABLE = "audit_logs"
    
    # ============================================================
    # 对象子对象包含配置
    # ============================================================
    
    OBJECT_CHILD_CONFIG = {
        'products': {
            'children': ['versions'],
            'children_query': {
                'versions': "SELECT id FROM versions WHERE product_id = ?",
            },
        },
        'versions': {
            'children': ['domains', 'business_objects'],
            'children_query': {
                'domains': "SELECT id FROM domains WHERE version_id = ?",
                'business_objects': "SELECT id FROM business_objects WHERE version_id = ?",
            },
        },
        'domains': {
            'children': ['sub_domains', 'business_objects'],
            'children_query': {
                'sub_domains': "SELECT id FROM sub_domains WHERE domain_id = ?",
                'business_objects': """
                    SELECT bo.id FROM business_objects bo
                    JOIN service_modules sm ON bo.service_module_id = sm.id
                    JOIN sub_domains sd ON sm.sub_domain_id = sd.id
                    WHERE sd.domain_id = ?
                """,
            },
        },
        'business_objects': {
            'children': ['annotations'],
            'children_query': {
                'annotations': "SELECT id FROM annotations WHERE target_type = 'business_object' AND target_id = ?",
            },
            'associations': ['relationships'],
            'association_query': {
                'relationships_source': "SELECT id FROM relationships WHERE source_bo_id = ?",
                'relationships_target': "SELECT id FROM relationships WHERE target_bo_id = ?",
            },
        },
        'users': {
            'associated_to': ['roles', 'user_groups'],
            'associated_from': ['user_groups'],
            'association_query': {
                'user_group_members': """
                    SELECT ug.id FROM user_groups ug
                    JOIN user_group_members ugm ON ug.id = ugm.user_group_id
                    WHERE ugm.user_id = ?
                """,
            },
        },
        'roles': {
            'associated_from': ['users', 'user_groups'],
            'children': ['role_permissions'],
        },
        'user_groups': {
            'associated_to': ['roles'],
            'associated_from': ['users'],
            'children': ['user_group_members'],
        },
    }
    
    def verify_object_perspective(
        self, object_type: str, object_id: Any
    ) -> ObjectPerspectiveResult:
        """
        验证对象视角的审计日志完整性
        
        Args:
            object_type: 对象类型
            object_id: 对象 ID
            
        Returns:
            ObjectPerspectiveResult
        """
        result = ObjectPerspectiveResult(
            valid=True,
            object_type=object_type,
            object_id=object_id
        )
        
        # Layer 1: 获取自身日志
        own_logs = self._get_own_logs(object_type, object_id)
        result.layers['own_logs'] = {
            'count': len(own_logs),
            'actions': list(set(log.get('action') for log in own_logs)),
            'verification': self.verify_batch(own_logs) if own_logs else None,
        }
        
        if result.layers['own_logs']['verification']:
            v = result.layers['own_logs']['verification']
            if v['invalid_count'] > 0:
                result.valid = False
                result.errors.append(
                    f"自身日志验证失败: {v['invalid_count']}/{v['total']} 无效"
                )
        
        # Layer 2: 获取关联日志
        assoc_logs_as_source, assoc_logs_as_target, rel_logs = \
            self._get_association_logs(object_type, object_id)
        
        result.layers['association_logs'] = {
            'as_source': {
                'count': len(assoc_logs_as_source),
                'actions': list(set(log.get('action') for log in assoc_logs_as_source)),
            },
            'as_target': {
                'count': len(assoc_logs_as_target),
                'actions': list(set(log.get('action') for log in assoc_logs_as_target)),
            },
            'relationships': {
                'count': len(rel_logs),
                'actions': list(set(log.get('action') for log in rel_logs)),
            },
        }
        
        # 验证关联日志的结构
        for log in assoc_logs_as_source + assoc_logs_as_target:
            self._verify_association_log_structure(log, result)
        
        for log in rel_logs:
            self._verify_relationship_log_structure(log, object_id, result)
        
        # Layer 3: 获取子对象日志
        cascade_logs, config_logs, children_summary = self._get_children_logs(
            object_type, object_id
        )
        result.layers['children_logs'] = children_summary
        
        # 验证子对象覆盖
        self._verify_child_coverage(object_type, object_id, children_summary, result)
        
        # 验证 _source 标注
        self._verify_source_annotations(
            own_logs, assoc_logs_as_source, assoc_logs_as_target,
            rel_logs, cascade_logs, config_logs, result
        )
        
        return result
    
    # ============================================================
    # Layer 1: 自身日志
    # ============================================================
    
    SUPPORTED_SOURCES = {'own', 'association_target', 'cascade_child', 'child_object', 'relationship'}
    
    def _get_own_logs(self, object_type: str, object_id: Any) -> List[Dict]:
        """获取对象自身的审计日志"""
        if not self.ds:
            return []
        
        filters = {
            'object_type': object_type,
            'object_id': str(object_id),
        }
        logs = list(self.ds.find(self.AUDIT_TABLE, filters=filters, order_by='created_at DESC'))
        for log in logs:
            log['_source'] = 'own'
        return logs
    
    # ============================================================
    # Layer 2: 关联日志
    # ============================================================
    
    def _get_association_logs(
        self, object_type: str, object_id: Any
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """
        获取关联日志
        
        Returns:
            (as_source, as_target, relationships)
        """
        as_source = []
        as_target = []
        rel_logs = []
        
        if not self.ds:
            return as_source, as_target, rel_logs
        
        obj_id_str = str(object_id)
        
        # 2a. 作为 source 的关联日志（自身日志中 action 为 ASSOCIATE/DISSOCIATE 的）
        as_source = list(self.ds.find(
            self.AUDIT_TABLE,
            filters={
                'object_type': object_type,
                'object_id': obj_id_str,
            },
            order_by='created_at DESC'
        ))
        as_source = [log for log in as_source 
                     if log.get('action') in ('ASSOCIATE', 'DISSOCIATE', 'ASSIGN', 'REVOKE')]
        
        # 2b. 作为 target 的关联日志（反向查询）
        # 查找 new_value/old_value JSON 中包含此对象信息的日志
        as_target = self._find_logs_referencing_target(object_type, obj_id_str)
        
        # 2c. Relationship 参与方日志
        config = self.OBJECT_CHILD_CONFIG.get(object_type, {})
        if 'associations' in config and 'relationships' in config['associations']:
            rel_logs = self._find_relationship_logs(object_type, obj_id_str)
        
        return as_source, as_target, rel_logs
    
    def _find_logs_referencing_target(
        self, target_type: str, target_id: str
    ) -> List[Dict]:
        """
        反向查询：查找以本对象为 target 的关联日志
        
        查询策略：
        1. 查找所有 ASSOCIATE/DISSOCIATE 日志
        2. 解析 new_value/old_value JSON
        3. 检查 target_type 和 target_id 是否匹配
        """
        if not self.ds:
            return []
        
        # 尝试通过 parent_object_type/parent_object_id 查找
        candidates = list(self.ds.find(
            self.AUDIT_TABLE,
            filters={
                'parent_object_type': target_type,
                'parent_object_id': target_id,
            },
            order_by='created_at DESC'
        ))
        candidates = [log for log in candidates
                      if log.get('action') in ('ASSOCIATE', 'DISSOCIATE', 'ASSIGN', 'REVOKE')]
        
        for log in candidates:
            log['_source'] = 'association_target'
        
        return candidates
    
    def _find_relationship_logs(
        self, object_type: str, object_id: str
    ) -> List[Dict]:
        """
        查找与对象相关的关系日志
        
        对象参与关系时，关系的审计日志 object_type 为 'relationships'
        需要查找 source_bo_id 或 target_bo_id 匹配的关系记录
        """
        if not self.ds:
            return []
        
        # 查找涉及此对象的 relationship IDs
        rel_ids_source = self._query_relationship_ids('source_bo_id', object_id)
        rel_ids_target = self._query_relationship_ids('target_bo_id', object_id)
        all_rel_ids = list(set(rel_ids_source + rel_ids_target))
        
        if not all_rel_ids:
            return []
        
        # 查询这些关系的审计日志
        rel_logs = []
        for rid in all_rel_ids:
            logs = list(self.ds.find(
                self.AUDIT_TABLE,
                filters={
                    'object_type': 'relationships',
                    'object_id': str(rid),
                },
                order_by='created_at DESC'
            ))
            for log in logs:
                log['_source'] = 'relationship'
            rel_logs.extend(logs)
        
        return rel_logs
    
    def _query_relationship_ids(self, field: str, value: str) -> List[int]:
        """查询涉及此对象的 relationship IDs"""
        try:
            raw = self.ds.execute(
                f"SELECT id FROM relationships WHERE {field} = ?",
                [int(value)]
            )
            if raw:
                return [r[0] for r in raw.fetchall()]
        except:
            pass
        return []
    
    def _verify_association_log_structure(
        self, log: Dict, result: ObjectPerspectiveResult
    ):
        """验证关联日志的结构完整性"""
        action = log.get('action', '')
        field_name = log.get('field_name', '')
        
        if action in ('ASSOCIATE', 'ASSIGN'):
            new_value = log.get('new_value')
            target_info = self._parse_target_info(new_value)
            
            if not target_info:
                result.warnings.append(
                    f"ASSOCIATE 日志缺少目标信息: {field_name}"
                )
                return
            
            missing = []
            if not target_info.get('target_type'):
                missing.append('target_type')
            if not target_info.get('target_id'):
                missing.append('target_id')
            if not target_info.get('target_key'):
                missing.append('target_key')
            if not target_info.get('target_display'):
                missing.append('target_display')
            
            if missing:
                result.warnings.append(
                    f"ASSOCIATE 目标信息不完整 (缺: {missing}): {field_name}"
                )
        
        elif action in ('DISSOCIATE', 'REVOKE'):
            old_value = log.get('old_value')
            target_info = self._parse_target_info(old_value)
            
            if not target_info:
                result.warnings.append(
                    f"DISSOCIATE 日志缺少目标信息: {field_name}"
                )
                return
            
            missing = []
            if not target_info.get('target_type'):
                missing.append('target_type')
            if not target_info.get('target_id'):
                missing.append('target_id')
            
            if missing:
                result.warnings.append(
                    f"DISSOCIATE 目标信息不完整 (缺: {missing}): {field_name}"
                )
    
    def _verify_relationship_log_structure(
        self, log: Dict, object_id: str, result: ObjectPerspectiveResult
    ):
        """验证关系日志的结构完整性"""
        field_name = log.get('field_name', '')
        new_value = log.get('new_value')
        old_value = log.get('old_value')
        
        is_source = field_name == 'source_bo_id'
        is_target = field_name == 'target_bo_id'
        
        if not is_source and not is_target:
            return
        
        # 检查是否记录了双方的完整信息
        if is_source:
            # source_bo_id 的 new_value 应包含源 BO 信息
            if new_value:
                target_info = self._parse_target_info(new_value)
                if target_info:
                    if not target_info.get('target_display'):
                        result.warnings.append(
                            f"关系源端缺少显示名称: source_bo_id={new_value}"
                        )
                else:
                    result.warnings.append(
                        f"关系源端缺少结构化信息: source_bo_id={new_value}"
                    )
        
        if is_target:
            # target_bo_id 的 new_value 应包含目标 BO 信息
            if new_value:
                target_info = self._parse_target_info(new_value)
                if target_info:
                    if not target_info.get('target_display'):
                        result.warnings.append(
                            f"关系目标端缺少显示名称: target_bo_id={new_value}"
                        )
                else:
                    result.warnings.append(
                        f"关系目标端缺少结构化信息: target_bo_id={new_value}"
                    )
    
    # ============================================================
    # Layer 3: 子对象日志
    # ============================================================
    
    def _get_children_logs(
        self, object_type: str, object_id: Any
    ) -> Tuple[List[Dict], List[Dict], Dict[str, Any]]:
        """
        获取子对象日志
        
        包括：
        1. 级联删除子对象（parent_object_type + parent_object_id）
        2. 模型配置的子对象
        
        Returns:
            (cascade_logs, config_logs, summary)
        """
        if not self.ds:
            return [], [], {}
        
        obj_id_str = str(object_id)
        
        # 3a. 级联删除子对象
        cascade_logs = list(self.ds.find(
            self.AUDIT_TABLE,
            filters={
                'parent_object_type': object_type,
                'parent_object_id': obj_id_str,
            },
            order_by='created_at DESC'
        ))
        for log in cascade_logs:
            log['_source'] = 'cascade_child'
        
        # 3b. 模型配置的子对象
        config_logs = self._get_configured_children_logs(object_type, object_id)
        
        all_children = cascade_logs + config_logs
        
        # 按子对象类型分组统计
        children_by_type = {}
        for log in all_children:
            child_type = log.get('object_type', 'unknown')
            if child_type not in children_by_type:
                children_by_type[child_type] = {'count': 0, 'actions': set()}
            children_by_type[child_type]['count'] += 1
            children_by_type[child_type]['actions'].add(log.get('action'))
        
        for ct in children_by_type:
            children_by_type[ct]['actions'] = list(children_by_type[ct]['actions'])
        
        summary = {
            'total_count': len(all_children),
            'cascade_count': len(cascade_logs),
            'configured_count': len(config_logs),
            'by_type': children_by_type,
        }
        
        return cascade_logs, config_logs, summary
    
    def _get_configured_children_logs(
        self, object_type: str, object_id: Any
    ) -> List[Dict]:
        """
        获取模型配置声明的子对象日志
        
        根据 OBJECT_CHILD_CONFIG 中的 children_query 查询
        """
        if not self.ds:
            return []
        
        config = self.OBJECT_CHILD_CONFIG.get(object_type, {})
        children_query = config.get('children_query', {})
        
        if not children_query:
            return []
        
        obj_id_int = int(object_id)
        all_logs = []
        
        for child_type, query_sql in children_query.items():
            try:
                raw = self.ds.execute(query_sql, [obj_id_int])
                if raw:
                    child_ids = [r[0] for r in raw.fetchall()]
                    
                    for cid in child_ids:
                        logs = list(self.ds.find(
                            self.AUDIT_TABLE,
                            filters={
                                'object_type': child_type,
                                'object_id': str(cid),
                            },
                            order_by='created_at DESC'
                        ))
                        for log in logs:
                            log['_from_child_of'] = {
                                'type': object_type,
                                'id': obj_id_int,
                            }
                            log['_child_type'] = child_type
                            log['_source'] = 'child_object'
                        all_logs.extend(logs)
            except Exception:
                pass
        
        return all_logs
    
    def _verify_child_coverage(
        self, object_type: str, object_id: Any,
        children_summary: Dict, result: ObjectPerspectiveResult
    ):
        """
        验证子对象覆盖完整性
        
        检查：
        1. 期望的子对象类型是否都有日志
        2. 子对象日志是否合计合理
        """
        config = self.OBJECT_CHILD_CONFIG.get(object_type, {})
        expected_children = config.get('children', [])
        
        if not expected_children:
            return
        
        actual_types = set(children_summary.get('by_type', {}).keys())
        missing_types = [ct for ct in expected_children if ct not in actual_types]
        
        if missing_types:
            result.warnings.append(
                f"期望子对象类型无日志: {missing_types}"
            )
    
    def _verify_source_annotations(
        self, own_logs: List[Dict], assoc_logs_as_source: List[Dict],
        assoc_logs_as_target: List[Dict], rel_logs: List[Dict],
        cascade_logs: List[Dict], config_logs: List[Dict],
        result: ObjectPerspectiveResult
    ):
        """
        验证 _source 标注的正确性
        
        检查：
        1. 每条日志都有有效的 _source 值
        2. _source 值在 SUPPORTED_SOURCES 中
        3. 每类日志的 _source 值正确
        """
        source_counts = {}
        all_logs_with_source = []
        
        for source_val, logs in [
            ('own', own_logs),
            ('own', [log for log in assoc_logs_as_source if log.get('action') in ('ASSOCIATE', 'DISSOCIATE', 'ASSIGN', 'REVOKE')]),
            ('association_target', assoc_logs_as_target),
            ('relationship', rel_logs),
            ('cascade_child', cascade_logs),
            ('child_object', config_logs),
        ]:
            for log in logs:
                actual_source = log.get('_source')
                if actual_source is None:
                    result.errors.append(
                        f"日志缺少 _source 标注: id={log.get('id')} "
                        f"object_type={log.get('object_type')} action={log.get('action')}"
                    )
                    result.valid = False
                elif actual_source not in self.SUPPORTED_SOURCES:
                    result.errors.append(
                        f"日志 _source 值无效: id={log.get('id')} "
                        f"_source={actual_source}"
                    )
                    result.valid = False
                elif actual_source != source_val:
                    result.warnings.append(
                        f"日志 _source 标注不匹配: id={log.get('id')} "
                        f"期望={source_val} 实际={actual_source} "
                        f"object_type={log.get('object_type')} action={log.get('action')}"
                    )
                
                source_counts[actual_source] = source_counts.get(actual_source, 0) + 1
                all_logs_with_source.append(log)
        
        result.layers['source_summary'] = {
            'counts': source_counts,
            'total_annotated': len(all_logs_with_source),
        }
    
    # ============================================================
    # 辅助方法
    # ============================================================
    
    def _parse_target_info(self, value: Any) -> Optional[Dict]:
        """解析目标对象信息（继承自父类）"""
        if not value:
            return None
        
        try:
            if isinstance(value, str):
                parsed = json.loads(value)
            elif isinstance(value, dict):
                parsed = value
            else:
                return None
            
            if 'target_type' in parsed or 'target_id' in parsed:
                return parsed
            
            return None
        except:
            return None


def create_object_verifier(data_source=None) -> ObjectAuditLogVerifier:
    """创建对象视角审计日志验证器"""
    return ObjectAuditLogVerifier(data_source)
