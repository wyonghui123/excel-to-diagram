from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json
import os
import csv
import re

from openpyxl import Workbook

from meta.core.datasource import DataSource


@dataclass
class AuditQuery:
    object_type: Optional[str] = None
    object_id: Optional[Any] = None
    action: Optional[str] = None
    user_id: Optional[Any] = None
    user_name: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    field_name: Optional[str] = None
    keyword: Optional[str] = None
    trace_id: Optional[str] = None
    transaction_id: Optional[str] = None
    agent_id: Optional[str] = None
    agent_session_id: Optional[str] = None
    tool_call_id: Optional[str] = None
    status: Optional[str] = None
    log_category: Optional[str] = None
    log_level: Optional[str] = None


@dataclass
class AuditRecord:
    id: Any
    object_type: str
    object_id: Any
    action: str
    field_name: str
    old_value: Any
    new_value: Any
    user_id: Any
    user_name: str
    ip_address: str
    user_agent: str
    created_at: str
    trace_id: Optional[str] = None
    transaction_id: Optional[str] = None
    status: Optional[str] = None
    agent_id: Optional[str] = None
    agent_session_id: Optional[str] = None
    tool_call_id: Optional[str] = None
    agent_reasoning: Optional[str] = None
    log_category: Optional[str] = None
    log_level: Optional[str] = None
    # [DECORATIVE] v2 字段（FR-LOG-005，Spec v1.0 实施 2026-06-05）— 全部 nullable 兼容 v1
    action_kind: Optional[str] = None       # 'instance' | 'static'
    outcome: Optional[str] = None          # 'success' | 'failure' | 'denied' | 'retry'
    parent_action_id: Optional[Any] = None # 批量聚合 FK
    error_message: Optional[str] = None    # 失败/拒绝原因
    retention_until: Optional[str] = None  # ISO 8601 截止（6 月）


class BatchAuditContext:
    """
    批量审计日志聚合上下文 (FR-LOG-007)
    【2026-06-05 Spec v1.0 实施】

    100 条记录创建 → 1 条 header + N 条 detail（parent_action_id 关联）
    对齐 Stripe batch events 模式

    用法:
        with BatchAuditContext(
            action='batch_create_users',
            object_type='user',
            audit_service=audit_svc,
            user_context={'user_id': 1, 'user_name': 'alice'},
        ) as batch:
            for user_data in user_list:
                result = await user_service.create(user_data)
                batch.add_detail(object_id=result.id, outcome='success')
    """
    def __init__(self, action: str, object_type: str, audit_service: 'AuditService',
                 user_context: dict, datasource=None):
        self.action = action
        self.object_type = object_type
        self.audit = audit_service
        self.user_ctx = user_context
        self.datasource = datasource
        self.header_id: Optional[Any] = None
        self.details_count = 0
        self._error_msg: Optional[str] = None

    def __enter__(self) -> 'BatchAuditContext':
        # 1. 创建 header（标记为 static + 批量）
        from meta.core.action_models import DEFAULT_RETENTION_DAYS
        from datetime import datetime, timedelta
        try:
            self.header_id = self.audit.create(AuditRecord(
                id=None,
                created_at=datetime.utcnow().isoformat(),
                object_type=self.object_type,
                object_id='batch',  # 标记为批量聚合
                action=self.action,
                field_name='',
                old_value=None,
                new_value=None,
                user_id=self.user_ctx.get('user_id', 0),
                user_name=self.user_ctx.get('user_name', 'system'),
                ip_address=self.user_ctx.get('ip_address', ''),
                user_agent=self.user_ctx.get('user_agent', ''),
                action_kind='static',  # 批量操作通常是 static
                outcome='success',  # 初始为 success，__exit__ 时根据异常更新
                retention_until=(datetime.utcnow() + timedelta(days=DEFAULT_RETENTION_DAYS)).isoformat(),
                log_category='business',
                log_level='INFO',
                status='success',
                error_message=None,
                parent_action_id=None,
            ))
        except Exception as e:
            # header 创建失败不应阻断主流程
            import logging
            logging.getLogger(__name__).error(f"[BatchAuditContext] Failed to create header: {e}")
            self.header_id = None
        return self

    def add_detail(self, object_id: Any, outcome: str = 'success', error_msg: Optional[str] = None,
                   field_name: str = '', old_value: Any = None, new_value: Any = None) -> None:
        """添加一条 detail（带 parent_action_id 关联）"""
        from meta.core.action_models import DEFAULT_RETENTION_DAYS
        from datetime import datetime, timedelta
        # detail 动作：把 batch_xxx 拆为 xxx
        detail_action = self.action
        if detail_action.startswith('batch_'):
            detail_action = detail_action[len('batch_'):]

        self.details_count += 1
        try:
            self.audit.create(AuditRecord(
                id=None,
                created_at=datetime.utcnow().isoformat(),
                object_type=self.object_type,
                object_id=object_id,
                action=detail_action,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                user_id=self.user_ctx.get('user_id', 0),
                user_name=self.user_ctx.get('user_name', 'system'),
                ip_address=self.user_ctx.get('ip_address', ''),
                user_agent=self.user_ctx.get('user_agent', ''),
                action_kind='instance',  # detail 都是 instance
                outcome=outcome,
                error_message=error_msg,
                parent_action_id=self.header_id,  # [DECORATIVE] v2 关键关联
                retention_until=(datetime.utcnow() + timedelta(days=DEFAULT_RETENTION_DAYS)).isoformat(),
                log_category='business',
                log_level='INFO' if outcome == 'success' else 'ERROR',
                status=outcome,
            ))
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"[BatchAuditContext] Failed to add detail: {e}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        # batch 整体失败时更新 header
        if exc_type and self.header_id is not None:
            self._error_msg = f"{exc_type.__name__}: {exc_val}"
            try:
                self.audit.update(self.header_id, outcome='failure', error_message=self._error_msg)
            except Exception:
                pass
        return False  # 不吞异常


class AuditService:

    AUDIT_TABLE = "audit_logs"
    
    # FK 字段模式（以 _id 结尾，但不是 id 本身）
    FK_FIELD_PATTERN = re.compile(r'^(?!id$).*_id$')
    
    # 对象标识字段名（存储在 extra_data 中）
    OBJECT_KEY_FIELD = 'audit_object_key'
    OBJECT_DISPLAY_FIELD = 'audit_object_display_name'
    
    # 功能开关（可通过配置关闭）
    ENABLE_OBJECT_IDENTITY = True
    ENABLE_FK_STRUCTURING = True

    def __init__(self, data_source: DataSource):
        self.ds = data_source

    def _get_object_identity(self, object_type: str, object_id: Any) -> Dict[str, str]:
        """
        获取对象标识（业务 key 和显示名称）
        
        Args:
            object_type: 对象类型
            object_id: 对象 ID
            
        Returns:
            {audit_object_key: ..., audit_object_display_name: ...}
        """
        if not self.ENABLE_OBJECT_IDENTITY:
            return {}
        
        if not object_type or not object_id:
            return {}
        
        try:
            # 尝试查询对象的 key 和 name/display_name
            # 支持的表名映射
            table_name = object_type
            
            # 查询对象
            records = self.ds.find(table_name, filters={'id': object_id})
            if not records:
                return {}
            
            record = records[0]
            result = {}
            
            # 获取业务 key
            key_value = record.get('key') or record.get('code') or record.get('name')
            if key_value:
                result[self.OBJECT_KEY_FIELD] = str(key_value)
            
            # 获取显示名称
            display_value = record.get('name') or record.get('display_name') or record.get('title')
            if display_value:
                result[self.OBJECT_DISPLAY_FIELD] = str(display_value)
            
            return result
            
        except Exception as e:
            # 查询失败时返回空（不影响日志写入）
            return {}

    def _structure_fk_value(self, field_name: str, value: Any) -> Any:
        """
        结构化 FK 值
        
        当字段名以 _id 结尾时，尝试解析目标对象信息
        
        Args:
            field_name: 字段名
            value: 字段值
            
        Returns:
            结构化 JSON 或原始值
        """
        if not self.ENABLE_FK_STRUCTURING:
            return value
        
        if not value:
            return value
        
        # 检查是否是 FK 字段
        if not self.FK_FIELD_PATTERN.match(field_name):
            return value
        
        # 如果已经是结构化 JSON，直接返回
        if isinstance(value, dict) and 'target_type' in value:
            return value
        if isinstance(value, str) and value.startswith('{') and 'target_type' in value:
            return value
        
        try:
            # 解析目标对象类型
            # 例如: service_module_id -> service_module
            target_type = field_name[:-3]  # 去掉 _id 后缀
            
            # 处理复数形式
            if target_type.endswith('s'):
                target_type = target_type[:-1]
            
            # 尝试转换值为整数
            try:
                target_id = int(value)
            except:
                target_id = value
            
            # 查询目标对象
            records = self.ds.find(target_type, filters={'id': target_id})
            
            if not records:
                # 查询失败，返回原始值
                return value
            
            record = records[0]
            
            # 构造结构化值
            result = {
                'target_type': target_type,
                'target_id': target_id,
            }
            
            # 添加业务 key
            key_value = record.get('key') or record.get('code')
            if key_value:
                result['target_key'] = str(key_value)
            
            # 添加显示名称
            display_value = record.get('name') or record.get('display_name') or record.get('title')
            if display_value:
                result['target_display'] = str(display_value)
            
            return json.dumps(result, ensure_ascii=False)
            
        except Exception as e:
            # 解析失败时返回原始值
            return value

    def _structure_fk_values_in_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        结构化数据中的所有 FK 值
        
        Args:
            data: 数据字典
            
        Returns:
            处理后的数据字典
        """
        if not data:
            return data
        
        result = {}
        for field, value in data.items():
            if self.FK_FIELD_PATTERN.match(field) and value:
                result[field] = self._structure_fk_value(field, value)
            else:
                result[field] = value
        
        return result

    def log(self, object_type: str, object_id: Any, action: str,
            user_id: Any = None, user_name: str = None,
            old_data: Dict[str, Any] = None, new_data: Dict[str, Any] = None,
            ip_address: str = None, user_agent: str = None,
            trace_id: str = None, transaction_id: str = None,
            agent_id: str = None, agent_session_id: str = None,
            tool_call_id: str = None, agent_reasoning: str = None,
            extra_data: Dict[str, Any] = None,
            field_name: str = None, old_value: Any = None, new_value: Any = None,
            parent_object_type: str = None, parent_object_id: Any = None,
            log_category: str = None, log_level: str = None,
            # [v3.18 FR-003/004/005/009/013] 新增参数
            outcome: str = "success", cascade: bool = False,
            retention_until: str = None,
            cascade_root_id: Any = None, cascade_root_action: str = None) -> bool:
        """
        写入审计日志

        增强功能：
        1. 自动添加对象标识（audit_object_key, audit_object_display_name）到 extra_data
        2. 自动结构化 FK 字段值（{target_type, target_id, target_key, target_display}）
        3. [v3.18] 自动 derive log_category (FR-003), log_level (FR-004), retention_until (FR-013)
        4. [v3.18] 写入 outcome / cascade_root_id / cascade_root_action (FR-005/009)
        """
        try:
            now = datetime.now().isoformat()

            # [FIX 2026-06-20 P2 v2] AuditService 入口处 auto-gen transaction_id/trace_id
            # 覆盖所有调用方: AuditInterceptor + AuditLogger + 4 个直接 INSERT 路径
            # (auth_api/user_api/user_reset_password/subflow_engine)
            if not transaction_id:
                import uuid as _uuid
                transaction_id = f"tx_{_uuid.uuid4().hex[:16]}"
            if not trace_id:
                import uuid as _uuid
                trace_id = f"tr_{_uuid.uuid4().hex[:16]}"

            # [FIX 2026-06-19 E.2] 强制 action 不能为空, 否则报 ERROR
            # 业务人员看到 '未识别操作' 是因为某些路径传入了空 action
            # 这里是入口拦截, 早于所有后续处理
            if not action or (isinstance(action, str) and action.strip().upper() in ('', 'NULL', 'NONE')):
                import logging as _logging
                _logging.getLogger(__name__).error(
                    f"[audit_service.log] action is empty/None! object_type={object_type} "
                    f"object_id={object_id} user_id={user_id} extra_data={extra_data}"
                )
                action = 'UNKNOWN'
                # 把这个错误也记下来, 方便排查
                if extra_data is None:
                    extra_data = {}
                extra_data['_action_validation_error'] = 'action was empty at log() entry'

            # [v3.18 FR-003/004/013] 自动 derive 缺失的 log_category/log_level/retention_until
            from meta.core.audit_constants import (
                derive_category, derive_level, retention_days,
            )
            if not log_category:
                log_category = derive_category(action, cascade=cascade)
            if not log_level:
                log_level = derive_level(action, outcome=outcome)
            if not retention_until:
                from datetime import timedelta
                days = retention_days(log_category)
                retention_until = (datetime.now() + timedelta(days=days)).isoformat()

            # 获取对象标识
            object_identity = self._get_object_identity(object_type, object_id)
            
            # 合并到 extra_data
            if object_identity:
                extra_data = extra_data or {}
                extra_data.update(object_identity)
            
            field_logs = []
            
            # 支持直接传递字段名和值
            if field_name:
                # FK 结构化
                structured_old = self._structure_fk_value(field_name, old_value) if old_value else ''
                structured_new = self._structure_fk_value(field_name, new_value) if new_value else ''
                
                field_logs.append({
                    'field_name': field_name,
                    'old_value': str(structured_old) if structured_old is not None else '',
                    'new_value': str(structured_new) if structured_new is not None else '',
                })
            
            elif action == 'CREATE' and new_data:
                # FK 结构化
                structured_data = self._structure_fk_values_in_data(new_data)
                for field, value in structured_data.items():
                    field_logs.append({
                        'field_name': field,
                        'old_value': '',
                        'new_value': str(value) if value is not None else '',
                    })
            
            elif action == 'UPDATE':
                if old_data and new_data:
                    # FK 结构化
                    structured_old = self._structure_fk_values_in_data(old_data)
                    structured_new = self._structure_fk_values_in_data(new_data)
                    
                    all_fields = set(list(structured_old.keys()) + list(structured_new.keys()))
                    for field in all_fields:
                        old_val = structured_old.get(field)
                        new_val = structured_new.get(field)
                        
                        if field not in structured_new:
                            continue
                        
                        old_str = str(old_val) if old_val is not None else ''
                        new_str = str(new_val) if new_val is not None else ''
                        if old_str != new_str:
                            field_logs.append({
                                'field_name': field,
                                'old_value': old_str,
                                'new_value': new_str,
                            })
                elif new_data:
                    # FK 结构化
                    structured_data = self._structure_fk_values_in_data(new_data)
                    for field, value in structured_data.items():
                        if value is not None and str(value):
                            field_logs.append({
                                'field_name': field,
                                'old_value': '',
                                'new_value': str(value) if value is not None else '',
                            })
            
            elif action == 'DELETE' and old_data:
                # FK 结构化
                structured_data = self._structure_fk_values_in_data(old_data)
                
                system_fields = {'id', 'created_at', 'updated_at'}
                redundant_prefixes = ('version_',)
                skip_fields = {'priority'}
                
                for field, value in structured_data.items():
                    if field in system_fields:
                        continue
                    if field in skip_fields:
                        continue
                    if field.startswith(redundant_prefixes):
                        continue
                    field_logs.append({
                        'field_name': field,
                        'old_value': str(value) if value is not None else '',
                        'new_value': '',
                    })
            
            elif action in ('ASSOCIATE', 'DISSOCIATE'):
                if field_name:
                    if action == 'ASSOCIATE' and new_data:
                        field_logs.append({
                            'field_name': field_name,
                            'old_value': '',
                            'new_value': json.dumps(new_data, ensure_ascii=False) if new_data else '',
                        })
                    elif action == 'DISSOCIATE' and old_data:
                        field_logs.append({
                            'field_name': field_name,
                            'old_value': json.dumps(old_data, ensure_ascii=False) if old_data else '',
                            'new_value': '',
                        })
                    else:
                        field_logs.append({
                            'field_name': field_name,
                            'old_value': '',
                            'new_value': '',
                        })
            
            if not field_logs:
                field_logs.append({
                    'field_name': '_record',
                    'old_value': '',
                    'new_value': action,
                })
            
            for field_log in field_logs:
                record = {
                    'object_type': object_type or '_unknown',
                    'object_id': str(object_id) if object_id is not None else '',
                    'action': action,
                    'field_name': field_log['field_name'],
                    'old_value': field_log['old_value'],
                    'new_value': field_log['new_value'],
                    'user_id': str(user_id) if user_id is not None else '',
                    'user_name': user_name or '',
                    'ip_address': ip_address or '',
                    'user_agent': user_agent or '',
                    'created_at': now,
                    'trace_id': trace_id,
                    'transaction_id': transaction_id,
                    'agent_id': agent_id,
                    'agent_session_id': agent_session_id,
                    'tool_call_id': tool_call_id,
                    'agent_reasoning': agent_reasoning,
                    'status': 'written',
                    'extra_data': json.dumps(extra_data) if extra_data else None,
                    'parent_object_type': parent_object_type,
                    'parent_object_id': str(parent_object_id) if parent_object_id is not None else None,
                    'log_category': log_category,
                    'log_level': log_level,
                    # [v3.18 FR-005/009/013] 新增字段
                    'outcome': outcome,
                    'retention_until': retention_until,
                    'cascade_root_id': str(cascade_root_id) if cascade_root_id is not None else None,
                    'cascade_root_action': cascade_root_action,
                }

                self.ds.insert(self.AUDIT_TABLE, record)
            
            if not getattr(self.ds, 'in_transaction', False):
                self.ds.commit()
            
            return True
            
        except Exception as e:
            print(f"Failed to write audit log: {e}")
            import traceback
            traceback.print_exc()
            
            try:
                self.ds.insert(self.AUDIT_TABLE, {
                    'object_type': object_type or '_unknown',
                    'object_id': str(object_id) if object_id is not None else '',
                    'action': action,
                    'field_name': '_error',
                    'old_value': '',
                    'new_value': str(e),
                    'user_id': str(user_id) if user_id is not None else '',
                    'user_name': user_name or '',
                    'created_at': datetime.now().isoformat(),
                    'status': 'failed',
                    'error_message': str(e),
                })
                if not getattr(self.ds, 'in_transaction', False):
                    self.ds.commit()
            except:
                pass
            
            return False

    def query(self, query: AuditQuery, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        filters = {}

        if query.object_type is not None:
            filters["object_type"] = query.object_type
        if query.object_id is not None:
            filters["object_id"] = query.object_id
        if query.action is not None:
            filters["action"] = query.action
        if query.user_id is not None:
            filters["user_id"] = query.user_id
        if query.user_name is not None:
            filters["user_name"] = query.user_name
        if query.field_name is not None:
            filters["field_name"] = query.field_name
        if query.trace_id is not None:
            filters["trace_id"] = query.trace_id
        if query.transaction_id is not None:
            filters["transaction_id"] = query.transaction_id
        if query.agent_id is not None:
            filters["agent_id"] = query.agent_id
        if query.agent_session_id is not None:
            filters["agent_session_id"] = query.agent_session_id
        if query.tool_call_id is not None:
            filters["tool_call_id"] = query.tool_call_id
        if query.status is not None:
            filters["status"] = query.status
        if query.log_category is not None:
            filters["log_category"] = query.log_category
        if query.log_level is not None:
            filters["log_level"] = query.log_level

        all_records = self.ds.find(self.AUDIT_TABLE, filters=filters, order_by="created_at DESC")

        if query.start_time is not None:
            all_records = [r for r in all_records if r.get("created_at", "") >= query.start_time]
        if query.end_time is not None:
            all_records = [r for r in all_records if r.get("created_at", "") <= query.end_time]
        if query.keyword is not None:
            keyword_lower = query.keyword.lower()
            all_records = [
                r for r in all_records
                if keyword_lower in str(r.get("old_value", "")).lower()
                or keyword_lower in str(r.get("new_value", "")).lower()
                or keyword_lower in str(r.get("field_name", "")).lower()
                or keyword_lower in str(r.get("object_type", "")).lower()
            ]

        total = len(all_records)
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        start = (page - 1) * page_size
        end = start + page_size
        page_records = all_records[start:end]

        records = []
        for r in page_records:
            records.append(AuditRecord(
                id=r.get("id"),
                object_type=r.get("object_type", ""),
                object_id=r.get("object_id"),
                action=r.get("action", ""),
                field_name=r.get("field_name", ""),
                old_value=r.get("old_value", ""),
                new_value=r.get("new_value", ""),
                user_id=r.get("user_id"),
                user_name=r.get("user_name", ""),
                ip_address=r.get("ip_address", ""),
                user_agent=r.get("user_agent", ""),
                created_at=r.get("created_at", ""),
                trace_id=r.get("trace_id"),
                transaction_id=r.get("transaction_id"),
                status=r.get("status", "written"),
                agent_id=r.get("agent_id"),
                agent_session_id=r.get("agent_session_id"),
                tool_call_id=r.get("tool_call_id"),
                agent_reasoning=r.get("agent_reasoning"),
            ))

        return {
            "data": records,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    # 字段优先级：取第一个非空字段作为对象的显示名
    _DISPLAY_FIELD_CANDIDATES = ('display_name', 'name', 'username', 'title', 'code')

    def _resolve_display_name(self, record: Dict[str, Any]) -> str:
        """从对象记录中取第一个非空的 display 字段"""
        for f in self._DISPLAY_FIELD_CANDIDATES:
            v = record.get(f)
            if v is not None and v != '':
                return str(v)
        return ''

    def _lookup_display_names(self, type_id_pairs) -> Dict[str, str]:
        """批量查 (type, id) -> display_name 映射。

        type_id_pairs: Iterable[Tuple[str, str]]
        返回: {(type, id): display_name}
        """
        result: Dict[str, str] = {}
        if not type_id_pairs:
            return result

        # 按 type 分组
        grouped: Dict[str, List[str]] = {}
        for t, i in type_id_pairs:
            if not t or i is None or i == '':
                continue
            grouped.setdefault(t, []).append(str(i))

        # 尝试从元模型 registry 获取 object_type -> table_name 映射
        type_to_table: Dict[str, str] = {}
        try:
            from meta.core.models import registry
            for ot in grouped.keys():
                mobj = registry.get(ot)
                if mobj and getattr(mobj, 'table_name', None):
                    type_to_table[ot] = mobj.table_name
        except Exception:
            pass

        for t, id_list in grouped.items():
            unique_ids = set(str(i) for i in id_list)
            table_name = type_to_table.get(t, t)
            try:
                # 优先按 id 列表查询（如果支持的话）；否则降级查全表
                try:
                    rows = self.ds.find(table_name, filters={'id': list(unique_ids)}) or []
                except Exception:
                    rows = self.ds.find(table_name) or []
                for row in rows:
                    rid = str(row.get('id'))
                    if rid in unique_ids:
                        dn = self._resolve_display_name(row)
                        if dn:
                            result[f"{t}::{rid}"] = dn
            except Exception:
                continue

        return result

    def get_object_history(self, object_type: str, object_id: Any,
                           include_children: bool = False) -> List[Dict[str, Any]]:
        filters = {
            "object_type": object_type,
            "object_id": object_id,
        }
        records = list(self.ds.find(self.AUDIT_TABLE, filters=filters, order_by="created_at DESC"))

        for r in records:
            r['_source'] = 'own'

        if include_children:
            try:
                parent_filters = {
                    "parent_object_type": object_type,
                    "parent_object_id": str(object_id),
                }
                children_records = self.ds.find(
                    self.AUDIT_TABLE, filters=parent_filters, order_by="created_at DESC"
                )
                for child in children_records:
                    child['_parent_type'] = object_type
                    child['_parent_id'] = object_id
                    if child.get('action') in ('ASSOCIATE', 'DISSOCIATE', 'ASSIGN', 'REVOKE'):
                        child['_source'] = 'association_target'
                    else:
                        child['_source'] = 'cascade_child'
                records = list(records) + list(children_records)
            except Exception as e:
                pass

        for r in records:
            parent_type = r.get('parent_object_type')
            parent_id = r.get('parent_object_id')
            if parent_type and parent_id:
                r['_cascade_from'] = {
                    'type': parent_type,
                    'id': parent_id,
                }

        # [FIX 2026-06-09] 为每条记录附上 object/parent 的 display name
        try:
            pairs = set()
            for r in records:
                ot = r.get('object_type')
                oid = r.get('object_id')
                if ot and oid is not None and oid != '':
                    pairs.add((ot, str(oid)))
                pt = r.get('parent_object_type')
                pid = r.get('parent_object_id')
                if pt and pid is not None and pid != '':
                    pairs.add((pt, str(pid)))
                # 关联日志的 old_data/new_data 里的 target_id 也要查
                for fld in ('old_data', 'new_data'):
                    payload = r.get(fld)
                    if isinstance(payload, dict):
                        tt = payload.get('target_type')
                        ti = payload.get('target_id')
                        if tt and ti is not None and ti != '':
                            pairs.add((tt, str(ti)))
            display_map = self._lookup_display_names(pairs)
            for r in records:
                ot = r.get('object_type')
                oid = r.get('object_id')
                if ot and oid is not None and oid != '':
                    dn = display_map.get(f"{ot}::{oid}")
                    if dn:
                        r['object_display'] = dn
                pt = r.get('parent_object_type')
                pid = r.get('parent_object_id')
                if pt and pid is not None and pid != '':
                    dn = display_map.get(f"{pt}::{pid}")
                    if dn:
                        r['parent_object_display'] = dn
                for fld in ('old_data', 'new_data'):
                    payload = r.get(fld)
                    if isinstance(payload, dict):
                        tt = payload.get('target_type')
                        ti = payload.get('target_id')
                        if tt and ti is not None and ti != '':
                            dn = display_map.get(f"{tt}::{ti}")
                            if dn and 'target_display' not in payload:
                                payload['target_display'] = dn
        except Exception as e:
            logging.getLogger(__name__).debug(f"[audit_service.get_object_history] display name enrichment failed: {e}")

        try:
            records = sorted(records, key=lambda r: r.get('created_at', ''), reverse=True)
        except Exception:
            pass

        return records

    def get_user_activities(self, user_id: Any, days: int = 30) -> Dict[str, Any]:
        start_time = (datetime.now() - timedelta(days=days)).isoformat()

        all_records = self.ds.find(self.AUDIT_TABLE, filters={"user_id": user_id})
        filtered = [r for r in all_records if r.get("created_at", "") >= start_time]

        action_counts = {}
        object_type_counts = {}
        daily_counts = {}

        for r in filtered:
            action = r.get("action", "UNKNOWN")
            action_counts[action] = action_counts.get(action, 0) + 1

            obj_type = r.get("object_type", "unknown")
            object_type_counts[obj_type] = object_type_counts.get(obj_type, 0) + 1

            created_at = r.get("created_at", "")
            if created_at:
                day = created_at[:10]
                daily_counts[day] = daily_counts.get(day, 0) + 1

        return {
            "user_id": user_id,
            "days": days,
            "total_actions": len(filtered),
            "action_counts": action_counts,
            "object_type_counts": object_type_counts,
            "daily_counts": daily_counts,
        }

    def get_change_summary(self, object_type: Optional[str] = None,
                           start_time: Optional[str] = None,
                           end_time: Optional[str] = None) -> Dict[str, Any]:
        filters = {}
        if object_type is not None:
            filters["object_type"] = object_type

        all_records = self.ds.find(self.AUDIT_TABLE, filters=filters)

        if start_time is not None:
            all_records = [r for r in all_records if r.get("created_at", "") >= start_time]
        if end_time is not None:
            all_records = [r for r in all_records if r.get("created_at", "") <= end_time]

        action_counts = {}
        object_type_counts = {}
        field_change_counts = {}
        user_counts = {}

        for r in all_records:
            action = r.get("action", "UNKNOWN")
            action_counts[action] = action_counts.get(action, 0) + 1

            obj_type = r.get("object_type", "unknown")
            object_type_counts[obj_type] = object_type_counts.get(obj_type, 0) + 1

            field_name = r.get("field_name", "")
            if field_name:
                field_change_counts[field_name] = field_change_counts.get(field_name, 0) + 1

            user_name = r.get("user_name", "")
            if user_name:
                user_counts[user_name] = user_counts.get(user_name, 0) + 1

        return {
            "total_changes": len(all_records),
            "action_counts": action_counts,
            "object_type_counts": object_type_counts,
            "field_change_counts": field_change_counts,
            "user_counts": user_counts,
            "start_time": start_time,
            "end_time": end_time,
        }

    def get_category_statistics(self, start_time: Optional[str] = None,
                                 end_time: Optional[str] = None) -> Dict[str, Any]:
        """
        获取按日志类型和级别统计
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            Dict: 统计结果
        """
        all_records = self.ds.find(self.AUDIT_TABLE, filters={})
        
        if start_time is not None:
            all_records = [r for r in all_records if r.get("created_at", "") >= start_time]
        if end_time is not None:
            all_records = [r for r in all_records if r.get("created_at", "") <= end_time]
        
        category_counts = {}
        level_counts = {}
        category_level_counts = {}
        
        for r in all_records:
            category = r.get("log_category", "business")
            level = r.get("log_level", "INFO")
            
            category_counts[category] = category_counts.get(category, 0) + 1
            level_counts[level] = level_counts.get(level, 0) + 1
            
            key = f"{category}:{level}"
            category_level_counts[key] = category_level_counts.get(key, 0) + 1
        
        return {
            "total": len(all_records),
            "by_category": category_counts,
            "by_level": level_counts,
            "by_category_level": category_level_counts,
            "start_time": start_time,
            "end_time": end_time,
        }

    def get_agent_activities(self, agent_id: str, days: int = 30) -> Dict[str, Any]:
        start_time = (datetime.now() - timedelta(days=days)).isoformat()

        all_records = self.ds.find(self.AUDIT_TABLE, filters={"agent_id": agent_id})
        filtered = [r for r in all_records if r.get("created_at", "") >= start_time]

        action_counts = {}
        object_type_counts = {}
        session_counts = {}
        tool_call_counts = {}

        for r in filtered:
            action = r.get("action", "UNKNOWN")
            action_counts[action] = action_counts.get(action, 0) + 1

            obj_type = r.get("object_type", "unknown")
            object_type_counts[obj_type] = object_type_counts.get(obj_type, 0) + 1

            session_id = r.get("agent_session_id", "unknown")
            session_counts[session_id] = session_counts.get(session_id, 0) + 1

            tc_id = r.get("tool_call_id", "")
            if tc_id:
                tool_call_counts[tc_id] = tool_call_counts.get(tc_id, 0) + 1

        return {
            "agent_id": agent_id,
            "days": days,
            "total_actions": len(filtered),
            "action_counts": action_counts,
            "object_type_counts": object_type_counts,
            "session_counts": session_counts,
            "tool_call_counts": tool_call_counts,
        }

    def get_failed_audit_logs(self, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        all_records = self.ds.find(self.AUDIT_TABLE, filters={"status": "failed"})
        total = len(all_records)
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "data": all_records[start:end],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def retry_failed_record(self, record_id: int) -> Dict[str, Any]:
        records = self.ds.find(self.AUDIT_TABLE, filters={"id": record_id})
        if not records:
            return {"success": False, "message": "记录不存在"}

        record = records[0]
        if record.get("status") != "failed":
            return {"success": False, "message": "记录状态不是failed，无需重试"}

        try:
            self.ds.update(
                self.AUDIT_TABLE,
                record_id,
                {"status": "written", "retry_count": (record.get("retry_count") or 0) + 1, "error_message": None}
            )
            if not self.ds.in_transaction:
                self.ds.commit()
            return {"success": True, "message": "重试成功，状态已更新为written"}
        except Exception as e:
            try:
                self.ds.update(
                    self.AUDIT_TABLE,
                    record_id,
                    {"retry_count": (record.get("retry_count") or 0) + 1, "error_message": str(e)}
                )
                if not self.ds.in_transaction:
                    self.ds.commit()
            except:
                pass
            return {"success": False, "message": "重试失败: %s" % str(e)}

    def export_audit_log(self, query: AuditQuery, format: str = "xlsx") -> str:
        result = self.query(query, page=1, page_size=1000000)
        records = result["data"]

        output_dir = os.path.join(os.getcwd(), "exports")
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if format.lower() == "csv":
            file_name = "audit_log_{0}.csv".format(timestamp)
            file_path = os.path.join(output_dir, file_name)

            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "id", "object_type", "object_id", "action", "field_name",
                    "old_value", "new_value", "user_id", "user_name",
                    "ip_address", "user_agent", "created_at"
                ])
                for r in records:
                    writer.writerow([
                        r.id, r.object_type, r.object_id, r.action, r.field_name,
                        r.old_value, r.new_value, r.user_id, r.user_name,
                        r.ip_address, r.user_agent, r.created_at
                    ])
            return file_path

        file_name = "audit_log_{0}.xlsx".format(timestamp)
        file_path = os.path.join(output_dir, file_name)

        wb = Workbook()
        ws = wb.active
        ws.title = "Audit Log"

        ws.append([
            "id", "object_type", "object_id", "action", "field_name",
            "old_value", "new_value", "user_id", "user_name",
            "ip_address", "user_agent", "created_at"
        ])

        for r in records:
            ws.append([
                r.id, r.object_type, r.object_id, r.action, r.field_name,
                r.old_value, r.new_value, r.user_id, r.user_name,
                r.ip_address, r.user_agent, r.created_at
            ])

        wb.save(file_path)
        wb.close()

        return file_path
