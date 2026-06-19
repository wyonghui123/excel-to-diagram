# -*- coding: utf-8 -*-
"""
Action 执行器 - 基于元模型定义执行 CRUD 操作

支持：
- 自动从 MetaObject 生成 SQL
- 基于 DataSource 抽象执行
- 参数绑定和类型转换
- 返回结果封装
- 规则自动执行（校验、计算、触发等）
- 审计日志自动记录
"""

from typing import List, Dict, Any, Optional, Type
from datetime import datetime
import uuid
import json
import logging
import secrets
import string

logger = logging.getLogger(__name__)

from meta.core.models import MetaObject, MetaField, MetaAction, ActionType, FieldType, RuleTrigger
from meta.core.datasource import DataSource
from meta.core.query_builder import QueryBuilder
from meta.core.rule_executor import RuleEngine, RuleExecutionReport
from meta.core.exceptions import ConcurrentModificationError
from meta.services.hierarchy_validation_service import validate_update, validate_delete
from meta.core.metadata_driven_validator import MetadataDrivenValidator
from meta.core.validation_messages import ValidationMessageRegistry


ERROR_MESSAGE_MAP = {
    "NOT NULL constraint failed": ValidationMessageRegistry.get("validation.field.required", field_name="字段"),
    "UNIQUE constraint failed": ValidationMessageRegistry.get("validation.field.unique", field_name="值"),
    "FOREIGN KEY constraint failed": ValidationMessageRegistry.get("validation.field.fk_not_found", target_name="关联对象", value=""),
    "CHECK constraint failed": "不满足校验条件",
    "INTEGER CONSTRAINT failed": "数值类型错误",
}


def translate_error_message(error_str: str, meta_object: MetaObject) -> str:
    """将数据库错误消息转换为业务友好消息
    
    Args:
        error_str: 原始错误消息
        meta_object: 元模型对象
        
    Returns:
        业务友好的错误消息
    """
    if not error_str:
        return "操作失败"
    
    error_lower = error_str.lower()
    
    for db_error, biz_message in ERROR_MESSAGE_MAP.items():
        if db_error.lower() in error_lower:
            match = re.search(r'([a-z_]+)\.(code|id|name)', error_str, re.IGNORECASE)
            if match:
                field_id = match.group(1)
                field = meta_object.get_field(field_id)
                if field:
                    field_name = field.semantics.meaning or field.name or field_id
                    return f"{field_name} {biz_message}"
                # 尝试从 registry 查找对应 MetaObject 的中文名
                from meta import get_meta_object
                ref_obj = get_meta_object(field_id)
                if ref_obj:
                    return f"{ref_obj.name} {biz_message}"
                return biz_message
            return biz_message
    
    return error_str


import re


class AuditLogger:
    """审计日志记录器"""
    
    AUDIT_TABLE = "audit_logs"
    
    def __init__(self, data_source: DataSource, enabled: bool = True):
        self.ds = data_source
        self.enabled = enabled
        self._current_user: Dict[str, Any] = {}
        self._agent_context: Dict[str, Any] = {}
    
    def set_user(self, user_id: Any = None, user_name: str = "", 
                 ip_address: str = "", user_agent: str = "") -> None:
        """设置当前用户信息"""
        self._current_user = {
            "user_id": user_id,
            "user_name": user_name,
            "ip_address": ip_address,
            "user_agent": user_agent,
        }
    
    def set_agent_context(self, agent_id: str = None, agent_session_id: str = None,
                          tool_call_id: str = None, agent_reasoning: str = None) -> None:
        """设置 Agent 上下文信息"""
        self._agent_context = {
            "agent_id": agent_id,
            "agent_session_id": agent_session_id,
            "tool_call_id": tool_call_id,
            "agent_reasoning": agent_reasoning,
        }
    
    def log(self, object_type: str, object_id: Any, action: str,
            field_name: str = "", old_value: Any = None, new_value: Any = None,
            extra_data: Dict[str, Any] = None,
            trace_id: str = None, transaction_id: str = None,
            parent_object_type: str = None, parent_object_id: Any = None,
            user_id: Any = None, user_name: str = None,
            ip_address: str = None, user_agent: str = None) -> bool:
        if not self.enabled:
            return True

        try:
            # 优先使用调用方显式传入的 user 信息（覆盖 _current_user）
            effective_user_id = user_id if user_id is not None else self._current_user.get("user_id")
            effective_user_name = user_name if user_name else (self._current_user.get("user_name") or "system")
            effective_ip = ip_address if ip_address is not None else self._current_user.get("ip_address", "")
            effective_ua = user_agent if user_agent is not None else self._current_user.get("user_agent", "")

            # [v3.18 FR-006] 标准化 user_name (display_name (username) 格式)
            from meta.core.audit_constants import normalize_user_name
            # 从 users 表查 display_name (如果 user_id 有)
            display_name = None
            if effective_user_id:
                try:
                    rows = self.ds.execute(
                        "SELECT display_name, username FROM users WHERE id = ?",
                        (effective_user_id,),
                    ).fetchall()
                    if rows:
                        display_name = rows[0][0] or None
                        # 用真实 username 覆盖 effective_user_name (避免是 "admin" 这种纯 username)
                        actual_username = rows[0][1]
                        if actual_username:
                            effective_user_name = normalize_user_name(display_name, actual_username)
                except Exception:
                    pass
            else:
                # 无 user_id, 用传入的 user_name 推断
                if effective_user_name and " (" not in effective_user_name and effective_user_name != "system":
                    # 已是 username, 没法 derive display_name
                    pass

            # [v3.18 FR-003/004/005/013] 委托给 AuditService.log() 自动 derive + 写 outcome/retention
            from meta.services.audit_service import AuditService
            # [v3.18 FR-005] 从 action 自动 derive outcome
            from meta.core.audit_constants import derive_outcome_from_action
            outcome = derive_outcome_from_action(action)

            # [v3.18] agent 上下文走 extra_data (AuditService.log 不直接接)
            if self._agent_context and any(self._agent_context.values()):
                extra_data = dict(extra_data or {})
                for k in ('agent_id', 'agent_session_id', 'tool_call_id', 'agent_reasoning'):
                    v = self._agent_context.get(k)
                    if v is not None:
                        extra_data[k] = v

            audit_svc = AuditService(self.ds)
            return audit_svc.log(
                object_type=object_type,
                object_id=object_id,
                action=action,
                field_name=field_name,
                old_value=self._serialize_value(old_value),
                new_value=self._serialize_value(new_value),
                extra_data=extra_data,
                trace_id=trace_id,
                transaction_id=transaction_id,
                parent_object_type=parent_object_type,
                parent_object_id=parent_object_id,
                user_id=effective_user_id,
                user_name=effective_user_name,
                ip_address=effective_ip,
                user_agent=effective_ua,
                outcome=outcome,  # 自动 derive (success/blocked/failure/retry)
            )
        except Exception as e:
            logger.error("AuditLogger failed to log: %s", str(e))
            return False

    def log_create(self, object_type: str, object_id: Any, data: Dict[str, Any],
                   trace_id: str = None, transaction_id: str = None,
                   parent_object_type: str = None, parent_object_id: Any = None,
                   user_id: Any = None, user_name: str = None,
                   ip_address: str = None, user_agent: str = None) -> bool:
        self.log(
            object_type=object_type,
            object_id=object_id,
            action="CREATE",
            extra_data={"data": data},
            trace_id=trace_id,
            transaction_id=transaction_id,
            parent_object_type=parent_object_type,
            parent_object_id=parent_object_id,
            user_id=user_id,
            user_name=user_name,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        for key, value in data.items():
            if key in ("updated_at", "updated_by", "id", "created_at", "created_by",
                       "updated_date", "created_date", "version", "password_hash",
                       "token", "secret", "tenant_id", "is_system"):
                continue
            self.log(
                object_type=object_type,
                object_id=object_id,
                action="CREATE",
                field_name=key,
                new_value=value,
                trace_id=trace_id,
                transaction_id=transaction_id,
                parent_object_type=parent_object_type,
                parent_object_id=parent_object_id,
                user_id=user_id,
                user_name=user_name,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return True

    def log_update(self, object_type: str, object_id: Any,
                   old_data: Dict[str, Any], new_data: Dict[str, Any],
                   trace_id: str = None, transaction_id: str = None,
                   parent_object_type: str = None, parent_object_id: Any = None,
                   user_id: Any = None, user_name: str = None,
                   ip_address: str = None, user_agent: str = None) -> bool:
        changes = self._detect_changes(old_data, new_data)
        
        for field, (old_val, new_val) in changes.items():
            self.log(
                object_type=object_type,
                object_id=object_id,
                action="UPDATE",
                field_name=field,
                old_value=old_val,
                new_value=new_val,
                trace_id=trace_id,
                transaction_id=transaction_id,
                parent_object_type=parent_object_type,
                parent_object_id=parent_object_id,
                user_id=user_id,
                user_name=user_name,
                ip_address=ip_address,
                user_agent=user_agent,
            )

        return True

    def log_delete(self, object_type: str, object_id: Any, data: Dict[str, Any],
                   trace_id: str = None, transaction_id: str = None,
                   parent_object_type: str = None, parent_object_id: Any = None,
                   user_id: Any = None, user_name: str = None,
                   ip_address: str = None, user_agent: str = None) -> bool:
        return self.log(
            object_type=object_type,
            object_id=object_id,
            action="DELETE",
            extra_data={"deleted_data": data},
            trace_id=trace_id,
            transaction_id=transaction_id,
            parent_object_type=parent_object_type,
            parent_object_id=parent_object_id,
            user_id=user_id,
            user_name=user_name,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    
    def _detect_changes(self, old_data: Dict[str, Any], new_data: Dict[str, Any]) -> Dict[str, tuple]:
        """检测变更的字段
        
        只比较 new_data 中实际存在的字段，
        避免将未提交的字段误判为"变为空"。
        """
        changes = {}
        
        for key in new_data.keys():
            if key in ["updated_at", "updated_by", "id", "created_at", "created_by"]:
                continue
            
            old_val = old_data.get(key)
            new_val = new_data.get(key)
            
            if old_val != new_val:
                changes[key] = (old_val, new_val)
        
        return changes
    
    def _serialize_value(self, value: Any) -> str:
        """序列化值"""
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)


class PseudoVariableResolver:

    def __init__(self, user_context: Dict[str, Any] = None):
        self._user_context = user_context or {}

    def resolve(self, expression: str) -> Any:
        if not expression or not expression.startswith('$'):
            return expression

        if expression == '$now':
            return datetime.now().isoformat()
        elif expression == '$user.id':
            return self._user_context.get('user_id', '')
        elif expression == '$user.name':
            return self._user_context.get('user_name', '')
        elif expression == '$uuid':
            import uuid
            return str(uuid.uuid4())
        else:
            return expression


class ActionResult:
    """Action 执行结果"""
    
    def __init__(self, success: bool = True, data: Any = None,
                 message: str = "", error: str = "", errors: list = None):
        self.success = success
        self.data = data
        self.message = message
        self.error = error
        self.errors = errors or []
        self.affected_rows = 0
        self.last_insert_id = None
        self.rule_report: Optional[RuleExecutionReport] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "error": self.error,
            "errors": self.errors,
            "affected_rows": self.affected_rows,
            "last_insert_id": self.last_insert_id,
        }

    @classmethod
    def ok(cls, data: Any = None, message: str = "") -> "ActionResult":
        return cls(success=True, data=data, message=message)

    @classmethod
    def fail(cls, error: str, message: str = "", errors: list = None) -> "ActionResult":
        return cls(success=False, error=error, message=message, errors=errors)


class ActionExecutor:
    """
    Action 执行器
    
    根据元模型定义自动执行 CRUD 操作，并自动执行相关规则。
    支持审计日志自动记录。
    集成冗余字段一致性保障（WriteGuard + CascadeGuard）。
    """
    
    def __init__(self, data_source: DataSource, rule_engine: Optional[RuleEngine] = None,
                 audit_enabled: bool = True):
        self.ds = data_source
        self.rule_engine = rule_engine or RuleEngine()
        self.audit_logger = AuditLogger(data_source, enabled=audit_enabled)
        self._pseudo_resolver = PseudoVariableResolver(self.audit_logger._current_user)
        self._request_context: Dict[str, Any] = {}
        
        from meta.core.consistency_guard import WriteGuard, CascadeGuard, ComputedFieldHandler
        from meta.core.redundancy_registry import redundancy_registry
        from meta.core.field_permission_checker import get_field_permission_checker
        self._write_guard = WriteGuard(data_source, redundancy_registry)
        self._cascade_guard = CascadeGuard(data_source, redundancy_registry)
        self._computed_field_handler = ComputedFieldHandler(data_source)
        self._field_perm_checker = get_field_permission_checker()
        self._validator = MetadataDrivenValidator(data_source)

    def set_request_context(self, context: Dict[str, Any]) -> None:
        self._request_context = context or {}

    def get_request_context(self) -> Dict[str, Any]:
        return self._request_context
    
    def set_audit_user(self, user_id: Any = None, user_name: str = "",
                       ip_address: str = "", user_agent: str = "") -> None:
        self.audit_logger.set_user(user_id, user_name, ip_address, user_agent)
        self._pseudo_resolver._user_context = self.audit_logger._current_user

    def set_agent_context(self, agent_id: str = None, agent_session_id: str = None,
                          tool_call_id: str = None, agent_reasoning: str = None) -> None:
        self.audit_logger.set_agent_context(agent_id, agent_session_id, tool_call_id, agent_reasoning)
    
    def enable_audit(self, enabled: bool = True) -> None:
        """启用/禁用审计日志"""
        self.audit_logger.enabled = enabled

    def _get_field_business_name(self, meta_object: MetaObject, field_id: str) -> str:
        """获取字段的业务名称"""
        field = meta_object.get_field(field_id)
        if field:
            return field.semantics.meaning or field.name or field_id
        return field_id

    def _get_business_key_fields(self, meta_object: MetaObject) -> List[MetaField]:
        """获取对象的业务键字段列表（支持组合键）"""
        bk_fields = []
        for field in meta_object.fields:
            if getattr(field.semantics, 'business_key', False):
                is_virtual = field.storage.value == 'virtual' or getattr(field.semantics, 'virtual', False)
                if not is_virtual:
                    bk_fields.append(field)
        return bk_fields

    def _validate_business_key_uniqueness(self, meta_object: MetaObject, data: Dict[str, Any], 
                                          exclude_id: Any = None) -> Optional[str]:
        """校验业务键唯一性（支持组合键）
        
        Args:
            meta_object: 元模型对象
            data: 数据字典
            exclude_id: 排除的记录ID（用于更新时排除自身）
            
        Returns:
            如果校验失败返回错误消息，否则返回 None
        """
        bk_fields = self._get_business_key_fields(meta_object)
        
        if not bk_fields:
            return None
        
        bk_values = []
        for bk_field in bk_fields:
            value = data.get(bk_field.id)
            if value is not None and str(value).strip() != "":
                bk_values.append((bk_field, str(value).strip()))
        
        if not bk_values:
            return None
        
        if len(bk_values) == 1:
            bk_field, bk_value = bk_values[0]
            query = f"SELECT id FROM {meta_object.table_name} WHERE {bk_field.db_column} = ?"
            params = [bk_value]
            # [SYMBOL] 关键修复：添加版本隔离条件
            has_version_id = any(f.id == 'version_id' for f in meta_object.fields)
            version_id_value = data.get('version_id')
            if has_version_id and version_id_value is not None:
                query += " AND version_id = ?"
                params.append(version_id_value)
            if exclude_id:
                query += " AND id != ?"
                params.append(exclude_id)
        else:
            where_clauses = []
            params = []
            for bk_field, bk_value in bk_values:
                where_clauses.append(f"{bk_field.db_column} = ?")
                params.append(bk_value)
            # [SYMBOL] 关键修复：添加版本隔离条件
            has_version_id = any(f.id == 'version_id' for f in meta_object.fields)
            version_id_value = data.get('version_id')
            if has_version_id and version_id_value is not None:
                where_clauses.append("version_id = ?")
                params.append(version_id_value)
            query = f"SELECT id FROM {meta_object.table_name} WHERE {' AND '.join(where_clauses)}"
            if exclude_id:
                query += " AND id != ?"
                params.append(exclude_id)
        
        try:
            cursor = self.ds.execute(query, tuple(params))
            row = cursor.fetchone()
            if row:
                bk_field_names = "、".join([f.name for f, v in bk_values])
                bk_value_str = " + ".join([v for f, v in bk_values])
                # [NEW v1.2.13 2026-06-19] 单字段时不显示"组合"
                if len(bk_values) == 1:
                    return ValidationMessageRegistry.get("validation.object.business_key_single",
                                                          field_name=bk_values[0][0].name,
                                                          value=bk_values[0][1])
                return ValidationMessageRegistry.get("validation.object.business_key_composite",
                                                       field_names=bk_field_names, values=bk_value_str)
        except Exception:
            pass

        return None

    def _find_by_key(self, object_type: str, key_field: str, key_value: Any,
                     version_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """根据关键字段查找记录

        Args:
            object_type: 对象类型
            key_field: 关键字段名
            key_value: 关键字段值
            version_id: 版本ID，如果指定则只在该版本内查找

        Returns:
            记录字典或 None
        """
        from meta import get_meta_object

        try:
            target_obj = get_meta_object(object_type)
            if not target_obj:
                return None

            query = f"SELECT * FROM {target_obj.table_name} WHERE {key_field} = ?"
            params = [key_value]

            has_version_id = any(f.id == 'version_id' for f in target_obj.fields)
            if has_version_id and version_id is not None:
                query += " AND version_id = ?"
                params.append(version_id)

            query += " LIMIT 1"

            cursor = self.ds.execute(query, tuple(params))
            row = cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"_find_by_key failed: {e}")

        return None

    def _resolve_foreign_keys(self, meta_object: MetaObject, data: Dict[str, Any], 
                               original_params: Dict[str, Any] = None) -> Dict[str, Any]:
        """解析外键：从业务键自动解析到技术ID

        参考 SAP @ObjectModel.foreignKey.association 注解

        Args:
            meta_object: 元模型对象
            data: 数据字典（已处理的数据）
            original_params: 原始参数（包含虚拟字段）

        Returns:
            解析后的数据字典

        Raises:
            ValueError: 如果父对象不存在
        """
        import logging
        logger = logging.getLogger(__name__)

        if original_params is None:
            original_params = data

        for field in meta_object.fields:
            resolve_from = getattr(field.semantics, 'resolve_from_field', None)
            resolve_to = getattr(field.semantics, 'resolve_to_object', None)

            if resolve_from and resolve_to:
                current_value = data.get(field.id) or data.get(field.db_column)
                source_value = original_params.get(resolve_from)

                if (current_value is None or current_value == '') and source_value:
                    logger.info(f"[FK Resolve] {meta_object.id}.{field.id}: "
                               f"从 {resolve_from}='{source_value}' 解析到 {resolve_to}")

                    version_id = original_params.get('version_id') or data.get('version_id')
                    parent_record = self._find_by_key(
                        resolve_to, 'code', source_value, version_id
                    )

                    if parent_record:
                        data[field.db_column] = parent_record.get('id')
                        logger.info(f"[FK Resolve] 成功: {field.db_column}={parent_record.get('id')}")
                    else:
                        from meta import get_meta_object
                        ref_obj = get_meta_object(resolve_to)
                        obj_name = ref_obj.name if ref_obj else resolve_to
                        raise ValueError(
                            f"父对象 {obj_name} 的业务键 '{source_value}' 不存在。"
                            f"请先创建 {obj_name} 或检查业务键是否正确。"
                        )

        return data

    def _validate_before_create(self, meta_object: MetaObject, data: Dict[str, Any]) -> Optional[ActionResult]:
        """在创建前进行元数据层校验（基于业务规则，而非数据库约束）

        校验层次（参考 SAP One Model）：
        1. 技术层校验 - required（数据库 NOT NULL）
        2. 业务层校验 - mandatory（@mandatory）
        3. 业务键校验 - business_key（@ObjectModel.businessKey，隐含必填）
        4. 唯一性校验 - unique/business_key 唯一性
        5. 格式校验 - pattern（正则匹配）
        6. 长度校验 - max_length
        7. 枚举校验 - enum_values
        8. FK存在性校验

        Returns:
            如果校验失败返回 ActionResult，否则返回 None
        """
        details = self._validator.validate_create(meta_object, data)
        if details:
            return ActionResult.fail(
                error="VALIDATION_FAILED",
                message="; ".join(d.message for d in details),
                errors=[d.to_dict() for d in details]
            )
        return None

    def _check_unique_constraint(self, meta_object: MetaObject, field: MetaField, field_value: Any) -> bool:
        """检查唯一性约束是否冲突

        Args:
            meta_object: 元数据对象
            field: 字段定义
            field_value: 字段值

        Returns:
            如果存在冲突返回 True，否则返回 False
        """
        try:
            query = f"SELECT COUNT(*) as cnt FROM {meta_object.table_name} WHERE {field.db_column} = ?"
            cursor = self.ds.execute(query, (field_value,))
            row = cursor.fetchone()
            return row[0] > 0 if row else False
        except Exception:
            return False

    def _validate_before_update(self, meta_object: MetaObject, data: Dict[str, Any],
                                 original_data: Optional[Dict[str, Any]] = None,
                                 exclude_id: Any = None) -> Optional[ActionResult]:
        """在更新前进行元数据层校验

        与 _validate_before_create 对称，覆盖：
        1. required 字段被清空校验
        2. mandatory 字段被清空校验
        3. business_key 字段被清空校验
        4. unique 字段冲突校验（排除自身）
        5. pattern 格式校验
        6. max_length 长度校验
        7. enum_values 枚举值校验
        8. FK 存在性校验
        9. business_key 组合唯一性（排除自身）
        10. indexes 复合唯一索引（排除自身）

        Returns:
            如果校验失败返回 ActionResult，否则返回 None
        """
        details = self._validator.validate_update(meta_object, data, original_data, exclude_id)
        if details:
            return ActionResult.fail(
                error="VALIDATION_FAILED",
                message="; ".join(d.message for d in details),
                errors=[d.to_dict() for d in details]
            )
        return None
    
    def execute(self, meta_object: MetaObject, action_id: str, 
                params: Optional[Dict[str, Any]] = None,
                skip_rules: bool = False) -> ActionResult:
        """
        执行指定的 Action
        
        Args:
            meta_object: 元模型对象
            action_id: Action ID (如 crud_create, crud_read)
            params: 参数字典
            skip_rules: 是否跳过规则执行
            
        Returns:
            ActionResult 执行结果
        """
        resolved_id = action_id
        if not meta_object.get_action(action_id) and action_id.startswith('crud_'):
            suffix = action_id[5:]
            alt_id = "{0}_{1}".format(meta_object.id, suffix)
            if meta_object.get_action(alt_id):
                resolved_id = alt_id

        action = meta_object.get_action(resolved_id)
        if not action:
            return ActionResult.fail(
                error="ACTION_NOT_FOUND",
                message="Action '{0}' not found in '{1}'".format(action_id, meta_object.id)
            )
        
        if not meta_object.persistent:
            return ActionResult.fail(
                error="OBJECT_NOT_PERSISTENT",
                message="Object '{0}' is not persistent".format(meta_object.id)
            )
        
        params = params or {}
        
        if action.action_type == ActionType.CRUD:
            return self._execute_crud(meta_object, action, params, skip_rules)
        elif action.action_type == ActionType.BATCH:
            return self._execute_batch(meta_object, action, params, skip_rules)
        elif action.action_type == ActionType.BUSINESS:
            return self._execute_business(meta_object, action, params)
        else:
            return ActionResult.fail(
                error="UNSUPPORTED_ACTION_TYPE",
                message="Action type '{0}' is not supported".format(action.action_type.value)
            )
    
    def _execute_crud(self, meta_object: MetaObject, action: MetaAction, 
                      params: Dict[str, Any], skip_rules: bool = False) -> ActionResult:
        """执行 CRUD Action"""
        method = action.method.upper()
        
        if method == "POST":
            return self._do_create(meta_object, params, skip_rules)
        elif method == "GET":
            if "id" in params:
                return self._do_read(meta_object, params)
            else:
                return self._do_list(meta_object, params)
        elif method == "PUT":
            return self._do_update(meta_object, params, skip_rules)
        elif method == "DELETE":
            return self._do_delete(meta_object, params, skip_rules)
        else:
            return ActionResult.fail(
                error="UNSUPPORTED_METHOD",
                message="HTTP method '{0}' is not supported".format(method)
            )

    def _check_deletability(self, meta_object: MetaObject, record: Dict[str, Any]) -> bool:
        if not meta_object.deletability or not meta_object.deletability.condition:
            return True
        from meta.core.condition_evaluator import ConditionEvaluator
        evaluator = ConditionEvaluator()
        return evaluator.evaluate(meta_object.deletability.condition, context={"self": record})

    def _check_addability(self, meta_object: MetaObject, data: Dict[str, Any]) -> Optional[str]:
        if not meta_object.addability or not meta_object.addability.condition:
            return None
        from meta.core.condition_evaluator import ConditionEvaluator
        evaluator = ConditionEvaluator()
        parent_data = self._resolve_parent_context_for_addability(meta_object, data)
        context = {"self": data, "parent": parent_data}
        can_add, msg = evaluator.evaluate_with_message(
            meta_object.addability.condition,
            meta_object.addability.message or ValidationMessageRegistry.get(
                "validation.object.addability_denied",
                message="当前条件不允许新增"
            ),
            context=context,
        )
        if not can_add:
            return msg
        return None

    def _resolve_parent_context_for_addability(self, meta_object: MetaObject, data: Dict[str, Any]) -> Dict[str, Any]:
        parent_object = getattr(meta_object, 'parent_object', None)
        if not parent_object:
            return {}
        hierarchy = getattr(meta_object, 'hierarchy', None)
        if not hierarchy:
            return {}
        parent_field = hierarchy.get('parent_field')
        if not parent_field:
            return {}
        parent_id = data.get(parent_field)
        if parent_id is None:
            return {}
        try:
            from meta import get_meta_object
            parent_meta = get_meta_object(parent_object)
            if parent_meta:
                parent_record = self.ds.find_by_id(parent_meta.table_name, parent_id)
                if parent_record:
                    return parent_record
        except Exception:
            pass
        return {}

    def _check_reverse_fk_references(self, meta_object: MetaObject, id_value: Any) -> List[str]:
        """检查是否有其他实体的 FK 字段引用了待删除记录"""
        from meta.core.models import registry as _model_registry
        errors = []
        all_objects = list(_model_registry.get_all().values())

        for other_obj in all_objects:
            if other_obj.id == meta_object.id:
                continue
            for f in other_obj.fields:
                resolve_to = getattr(f.semantics, 'resolve_to_object', None)
                parent_key = getattr(f.semantics, 'parent_key', False)
                target_object = resolve_to or (self._infer_fk_target(f) if parent_key else None)
                if target_object != meta_object.id:
                    continue

                cascade_delete = False
                if hasattr(other_obj, 'relations'):
                    for rel in other_obj.relations:
                        if isinstance(rel, dict):
                            if rel.get('target') == meta_object.id and rel.get('cascade_delete', False):
                                cascade_delete = True
                                break

                if cascade_delete:
                    continue

                try:
                    query = f"SELECT COUNT(*) FROM {other_obj.table_name} WHERE {f.db_column} = ?"
                    cursor = self.ds.execute(query, (id_value,))
                    row = cursor.fetchone()
                    count = row[0] if row else 0
                    if count > 0:
                        child_name = other_obj.name or other_obj.id
                        field_name = f.name or f.id
                        # 尝试从 other_obj 解析更友好的字段名
                        for of in other_obj.fields:
                            if getattr(of, 'db_column', None) == f.id or of.id == f.id:
                                field_name = of.name or f.name or f.id
                                break
                        errors.append(
                            ValidationMessageRegistry.get("validation.object.restrict_on_delete",
                                                           child_name=child_name,
                                                           field_name=field_name,
                                                           count=count)
                        )
                except Exception:
                    pass
        return errors

    def _infer_fk_target(self, field: MetaField) -> Optional[str]:
        field_id = field.id
        if field_id.endswith('_id'):
            candidate = field_id[:-3]
            from meta import get_meta_object
            if get_meta_object(candidate):
                return candidate
        return None

    def _check_deletion_policy_restrict(self, meta_object: MetaObject, id_value: Any) -> List[str]:
        """检查 deletion_policy.restrict_on 规则

        [FIX 2026-06-12] 兼容两种 rule 格式:
        - RestrictRule dataclass（yaml_loader.parse_deletion_policy 解析出的格式）:
            table / foreign_key / message
        - dict 格式（老格式，向后兼容）:
            target_object/target + fk_field/field + message
        也支持直接从 dict 读取 table/foreign_key 键。

        之前 bug：YAML 里的 restrict_on 规则被解析为 RestrictRule dataclass，
        旧代码只识别 dict 格式，导致规则被静默跳过 → 删 product（含 versions）不报错
        → SQL FK 违反被吞，删除看似"成功"实际未删。
        """
        errors = []
        deletion_policy = getattr(meta_object, 'deletion_policy', None)
        if not deletion_policy:
            return errors

        restrict_rules = []
        if isinstance(deletion_policy, dict):
            restrict_rules = deletion_policy.get('restrict_on', [])
        elif hasattr(deletion_policy, 'restrict_on'):
            restrict_rules = deletion_policy.restrict_on or []

        for rule in restrict_rules:
            # 兼容 RestrictRule dataclass + dict
            if hasattr(rule, 'table') and hasattr(rule, 'foreign_key'):
                target_table = rule.table
                fk_field = rule.foreign_key
                message = getattr(rule, 'message', '') or ''
            elif isinstance(rule, dict):
                target_table = rule.get('table')
                target_object = rule.get('target_object') or rule.get('target')
                target_table = target_table or target_object
                fk_field = rule.get('foreign_key') or rule.get('fk_field') or rule.get('field')
                message = rule.get('message', '') or ''
            else:
                continue
            if not target_table or not fk_field:
                continue
            try:
                query = f"SELECT COUNT(*) FROM {target_table} WHERE {fk_field} = ?"
                cursor = self.ds.execute(query, (id_value,))
                row = cursor.fetchone()
                count = row[0] if row else 0
                if count > 0:
                    # 将技术表名/FK字段名解析为用户友好的名称
                    from meta import get_meta_object
                    from meta.core.models import registry as _model_registry
                    child_obj = None
                    # 尝试从 target_object 或 target_table 反查 MetaObject
                    target_object_id = (rule.get('target_object') or rule.get('target')) if isinstance(rule, dict) else getattr(rule, 'target_object', None) or getattr(rule, 'target', None)
                    if target_object_id:
                        child_obj = get_meta_object(target_object_id)
                    if not child_obj:
                        # 尝试用 target_table 反查
                        for obj_id in _model_registry._objects:
                            mo = _model_registry.get(obj_id)
                            if mo and getattr(mo, 'table_name', '') == target_table:
                                child_obj = mo
                                break
                    child_name = child_obj.name if child_obj else target_table
                    # FK 字段名解析
                    fk_field_name = fk_field
                    if child_obj:
                        for f in child_obj.fields:
                            if getattr(f, 'db_column', None) == fk_field or f.id == fk_field:
                                fk_field_name = f.name or f.id
                                break
                    msg = message or ValidationMessageRegistry.get(
                        "validation.object.restrict_on_delete",
                        child_name=child_name, field_name=fk_field_name, count=count
                    )
                    errors.append(msg)
            except Exception as e:
                logger.warning(
                    f"[_check_deletion_policy_restrict] table={target_table} "
                    f"fk={fk_field} 查询失败: {e}"
                )
        return errors

    def _cleanup_m2m_tables(self, meta_object: MetaObject, id_value: Any):
        """删除记录时自动清理 M2M 中间表中的关联行

        [FIX 2026-06-10] 级联删除前先 SELECT 待删行，每条删除记录一条 DISSOCIATE 审计日志。
        修复 bug：删除 user_group 时，user_group_members / group_roles 等中间表被级联清空，
        但 audit_logs 表无任何记录，导致审计链断裂。

        注：meta_object.associations 是 dict[str, AssociationDefinition]，
        不是 list[dict]，要按 key 取值再读字段。
        """
        import sys
        associations = getattr(meta_object, 'associations', None)
        if not associations:
            return
        for assoc_name, assoc in associations.items():
            # 支持 dict 与 dataclass 两种形态
            if isinstance(assoc, dict):
                _get = lambda k, default=None: assoc.get(k, default)
            else:
                _get = lambda k, default=None: getattr(assoc, k, default)

            through = _get('through')
            if not through:
                continue
            source_key = _get('source_key')
            target_key = _get('target_key')
            target_type = _get('target_type') or _get('target_entity')
            assoc_label = _get('name') or assoc_name or through
            if not source_key:
                continue
            try:
                # 1) 先 SELECT 待删的 target IDs（用于写审计）
                pending_targets: list = []
                if target_key:
                    try:
                        select_cursor = self.ds.execute(
                            f"SELECT {target_key} FROM {through} WHERE {source_key} = ?",
                            (id_value,),
                        )
                        pending_targets = [row[0] for row in select_cursor.fetchall()]
                    except Exception as sel_err:
                        logger.warning(f"[M2M Cleanup] Failed to pre-select from {through}: {sel_err}")

                # 2) 执行级联删除
                self.ds.execute(f"DELETE FROM {through} WHERE {source_key} = ?", (id_value,))
                logger.info(
                    f"[M2M Cleanup] Deleted {len(pending_targets)} rows from {through} "
                    f"where {source_key}={id_value}"
                )

                # 3) 每条删除写一条 DISSOCIATE 审计日志（object_type=父对象）
                for tgt_id in pending_targets:
                    try:
                        self.audit_logger.log(
                            object_type=meta_object.id,
                            object_id=id_value,
                            action='DISSOCIATE',
                            field_name=str(assoc_label),
                            old_value={'target_type': target_type, 'target_id': tgt_id}
                                if target_type else {'target_id': tgt_id},
                            new_value=None,
                            parent_object_type=target_type,
                            parent_object_id=tgt_id,
                            extra_data={
                                'cascade_reason': f'{meta_object.id}#{id_value} deletion',
                                'through_table': through,
                            },
                        )
                    except Exception as audit_err:
                        logger.warning(
                            f"[M2M Cleanup] Failed to write DISSOCIATE audit for "
                            f"{meta_object.id}#{id_value} -/-> {target_type}#{tgt_id}: {audit_err}"
                        )
            except Exception as e:
                logger.warning(f"[M2M Cleanup] Failed to clean {through}: {e}")

    def _resolve_parent_info(self, meta_object: MetaObject, data: Dict[str, Any]) -> tuple:
        """解析对象的父对象信息 (parent_object_type, parent_object_id)

        解析策略 (按优先级):
        1) 标准的 hierarchy.parent_object + hierarchy.parent_field (普通父子对象, 如 sub_domain.domain_id)
        2) [FIX 2026-06-14] 多态关联 (polymorphic association): data 中同时存在
           target_type + target_id 字段 (如 annotation 备注, 关联到任意对象 domain/sub_domain/...)
           这种情况下, 父对象类型由 data.target_type 动态决定.
        3) 都没匹配: 返回 (None, None) — 顶级对象 (如 user/role)
        """
        parent_object_type = meta_object.parent_object
        if parent_object_type and meta_object.hierarchy:
            parent_field = meta_object.hierarchy.get('parent_field')
            if parent_field:
                parent_id = data.get(parent_field)
                if parent_id is not None:
                    return (parent_object_type, parent_id)

        # [FIX 2026-06-14] 多态关联 (polymorphic association) fallback:
        # 检测 data 中是否有 target_type + target_id 字段 (例如 annotation 备注)
        # 如果有, 返回 (data['target_type'], data['target_id']) 作为 parent.
        # 这样 domain/子领域/关系详情页的"操作日志" tab 就能看到关联的备注变更记录.
        if data and 'target_type' in data and 'target_id' in data:
            target_type = data.get('target_type')
            target_id = data.get('target_id')
            if target_type and target_id is not None:
                return (target_type, target_id)

        return (None, None)

    def _do_create(self, meta_object: MetaObject, params: Dict[str, Any],
                   skip_rules: bool = False) -> ActionResult:
        """执行创建操作"""
        logger.info(f"[ActionExecutor] _do_create START: object={meta_object.id}, params={params}")

        fields = meta_object.get_persistent_fields()
        data = self._prepare_data(fields, params, for_create=True)

        if data is None:
            return ActionResult.fail(
                error="INVALID_DATA",
                message="Failed to prepare data for create"
            )

        # [FIX 2026-06-08] user 对象特殊处理 password 字段（virtual: true）
        # 因为 password 字段在 user.yaml 里 semantics.virtual=true，get_persistent_fields()
        # 会跳过它，所以 _prepare_data 不会把 params['password'] 写入 data['password_hash']。
        # 必须在这里手动处理：1) 若 admin 传了 password 则哈希后写入；2) 否则自动生成
        _generated_temp_password = None
        _admin_password = None
        if meta_object.id == 'user':
            from meta.services.auth_provider import _hash_password_pbdkdf2
            _admin_password = params.get('password', '').strip() if params.get('password') else ''
            try:
                if _admin_password:
                    # admin 显式填了密码：用 admin 填的密码
                    if len(_admin_password) < 6:
                        return ActionResult.fail(
                            error="PASSWORD_TOO_SHORT",
                            message="密码长度不能少于 6 位"
                        )
                    data['password_hash'] = _hash_password_pbdkdf2(_admin_password)
                    logger.info(
                        f"[ActionExecutor] Using admin-provided password for user create"
                    )
                elif not data.get('password_hash'):
                    # admin 没填：自动生成 12 位强随机密码
                    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
                    _generated_temp_password = ''.join(
                        secrets.choice(alphabet) for _ in range(12)
                    )
                    data['password_hash'] = _hash_password_pbdkdf2(_generated_temp_password)
                    logger.info(
                        f"[ActionExecutor] Auto-generated temp password for user "
                        f"create (length=12)"
                    )
                # 首次登录强制改密（仅在自动生成或未设时）
                if _generated_temp_password and not data.get('must_change_password'):
                    data['must_change_password'] = 1
            except Exception as _e:
                logger.error(f"[ActionExecutor] Failed to process user password: {_e}")
                # 失败则继续由后端流程兜底

        try:
            data = self._resolve_foreign_keys(meta_object, data, params)
        except ValueError as e:
            return ActionResult.fail(
                error="FOREIGN_KEY_RESOLUTION_FAILED",
                message=str(e)
            )
        
        data = self._write_guard.on_before_save(meta_object.id, data)
        data = self._computed_field_handler.on_before_save(meta_object.id, data)

        if not skip_rules:
            addability_msg = self._check_addability(meta_object, data)
            if addability_msg:
                return ActionResult.fail(
                    error="ADDABILITY_DENIED",
                    message=addability_msg
                )

            validation_result = self._validate_before_create(meta_object, data)
            logger.info(f"[ActionExecutor] validation_result: {validation_result}")
            if validation_result:
                logger.info(f"[ActionExecutor] Validation FAILED, returning error: {validation_result.message}")
                return validation_result

            report = self.rule_engine.execute_rules(
                meta_object, RuleTrigger.BEFORE_CREATE, data
            )
            if not report.success:
                result = ActionResult.fail(
                    error="VALIDATION_FAILED",
                    message="Before create validation failed"
                )
                result.rule_report = report
                return result

            report = self.rule_engine.execute_rules(
                meta_object, RuleTrigger.BEFORE_SAVE, data
            )
            if not report.success:
                result = ActionResult.fail(
                    error="VALIDATION_FAILED",
                    message="Before save validation failed"
                )
                result.rule_report = report
                return result

            data = self.rule_engine.compute(meta_object, data)
        
        data = self._compute_hierarchy_path(meta_object, data, params)
        
        try:
            with self.ds.transaction():
                last_id = self.ds.insert(meta_object.table_name, data)
                
                if meta_object.get_hierarchy_path_field():
                    self.ds.update(meta_object.table_name, last_id, {
                        meta_object.get_hierarchy_path_field().db_column: str(last_id)
                    })
                    data["id"] = last_id
                    data = self._compute_hierarchy_path(meta_object, data, params)
                    self.ds.update(meta_object.table_name, last_id, {
                        meta_object.get_hierarchy_path_field().db_column: data[meta_object.get_hierarchy_path_field().db_column]
                    })
                
                if not skip_rules:
                    data["id"] = last_id
                    self.rule_engine.execute_rules(
                        meta_object, RuleTrigger.AFTER_CREATE, data
                    )
                    self.rule_engine.execute_rules(
                        meta_object, RuleTrigger.AFTER_SAVE, data
                    )
            
            parent_type, parent_id = self._resolve_parent_info(meta_object, data)
            def _audit_create(trace_id=None, transaction_id=None, user_id=None, user_name=None, ip_address=None, user_agent=None):
                return self.audit_logger.log_create(
                    object_type=meta_object.id,
                    object_id=last_id,
                    data=data,
                    trace_id=trace_id,
                    transaction_id=transaction_id,
                    parent_object_type=parent_type,
                    parent_object_id=parent_id,
                    user_id=user_id,
                    user_name=user_name,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            self._write_audit_log_v2(_audit_create)

            self._trigger_aggregate_refresh(meta_object.id, last_id, "created")

            result_data = {"id": last_id}
            # [NEW] 2026-06-08: 若为 user 自动生成了临时密码，返回明文供 admin 告知用户
            if _generated_temp_password is not None:
                result_data["generated_temp_password"] = _generated_temp_password
                result_data["must_change_password"] = True

            result = ActionResult.ok(
                data=result_data,
                message="{0} created successfully".format(meta_object.name)
            )
            result.last_insert_id = last_id
            result.affected_rows = 1
            return result
        except Exception as e:
            import traceback
            raw_error = str(e)
            logger.error(f"[_do_create] RAW ERROR: {raw_error}")
            logger.error(f"[_do_create] TRACEBACK: {traceback.format_exc()}")
            logger.error(f"[_do_create] table={meta_object.table_name}, data keys={list(data.keys()) if data else 'None'}")
            return ActionResult.fail(
                error="CREATE_FAILED",
                message=translate_error_message(raw_error, meta_object)
            )
    
    def _do_read(self, meta_object: MetaObject, params: Dict[str, Any]) -> ActionResult:
        """执行读取单条操作"""
        id_value = params.get("id")
        if id_value is None:
            return ActionResult.fail(
                error="MISSING_ID",
                message="Parameter 'id' is required"
            )
        
        try:
            record = self.ds.find_by_id(meta_object.table_name, id_value)
            if record:
                record = self._enrich_read_record(meta_object, record)
                return ActionResult.ok(data=record)
            else:
                return ActionResult.fail(
                    error="NOT_FOUND",
                    message="{0} with id={1} not found".format(meta_object.name, id_value)
                )
        except Exception as e:
            return ActionResult.fail(
                error="READ_FAILED",
                message=str(e)
            )

    def _enrich_read_record(self, meta_object, record):
        """SSOT: 单条读取时从 audit_logs 补全虚拟字段（updated_at 等）"""
        from meta.core.models import FieldStorage

        if not record:
            return record

        virtual_fields = []
        for f in meta_object.fields:
            storage = getattr(f, 'storage', None)
            deriv_obj = getattr(f, 'derive_from_object', '')
            if storage == FieldStorage.VIRTUAL and deriv_obj == 'audit_logs':
                virtual_fields.append(f)

        if not virtual_fields:
            return record

        object_id = str(record.get('id'))
        object_type = meta_object.id

        for vf in virtual_fields:
            field_id = vf.id
            try:
                rows = self.ds.query(
                    "SELECT MAX(created_at_epoch) as max_epoch, MAX(created_at) as max_iso "
                    "FROM audit_logs WHERE object_type = ? AND object_id = ? "
                    "AND action IN ('CREATE', 'UPDATE')",
                    [object_type, object_id]
                )
                if rows and rows[0]:
                    row = rows[0]
                    epoch_val = row.get('max_epoch')
                    iso_val = row.get('max_iso')
                    if epoch_val is not None:
                        from datetime import datetime
                        dt = datetime.fromtimestamp(epoch_val / 1000.0)
                        record[field_id] = dt.isoformat()
                    elif iso_val is not None:
                        record[field_id] = iso_val
            except Exception:
                pass

            if field_id not in record or record.get(field_id) is None:
                record[field_id] = record.get('created_at')

        return record

    def _do_list(self, meta_object: MetaObject, params: Dict[str, Any]) -> ActionResult:
        """执行列表查询操作"""
        # 提取特殊参数
        order_by = params.get("_order_by")
        limit = params.get("_limit")
        offset = params.get("_offset")

        import os
        try:
            with open(r'D:\filework\excel-to-diagram\logs\_dbg_do_list.log', 'a', encoding='utf-8') as f:
                f.write(f"\n=== _do_list obj={meta_object.id} table={meta_object.table_name} params_keys={list(params.keys())} ===\n")
                # 看 context.extra
                try:
                    from flask import g
                    extra = getattr(g, 'context_extra', None) or {}
                    f.write(f"  g.context_extra={extra}\n")
                except Exception as e:
                    f.write(f"  g.context_extra err: {e}\n")
        except Exception:
            pass

        logger.info(f"[_do_list] order_by={order_by}, limit={limit}, offset={offset}")

        # 构建过滤条件（排除特殊参数）
        filters = {}
        special_params = ["_order_by", "_limit", "_offset", "page", "page_size"]
        for key, value in params.items():
            if key not in special_params:
                # 检查是否是元数据字段
                field = meta_object.get_field(key)
                if field:
                    filters[field.db_column] = value
                    logger.info(f"[_do_list] filter: {field.db_column} = {value}")

        logger.info(f"[_do_list] final filters: {filters}")

        # [FIX 2026-06-11] 检测 order_by 是否引用虚拟字段 (storage=VIRTUAL / computed)
        # 虚拟字段不在 DB 中, ds.find 会静默 fallback 到默认排序.
        # 这条路径委托给 QueryService.search(), 它正确处理 count_relations / count_children 等子查询排序.
        # 注: v3.18 之后 crud_query 实际走 persistence_interceptor._do_list, 此处保留作为 fallback 路径.
        if order_by:
            from meta.core.models import FieldStorage
            bare = order_by.lstrip('-')
            order_field = meta_object.get_field(bare)
            is_virtual = False
            if order_field:
                storage = getattr(order_field, 'storage', None)
                if storage == FieldStorage.VIRTUAL or getattr(order_field, 'computed', False):
                    is_virtual = True
            if is_virtual:
                logger.info(f"[_do_list] Virtual field order detected: {order_by}, routing to QueryService.search()")
                try:
                    from meta.services.query_service import QueryService, SearchRequest, QueryCondition
                    qs = QueryService(self.ds)
                    page = (int(offset or 0) // int(limit or 20)) + 1 if limit else 1
                    page_size = int(limit or 20)
                    conditions = []
                    for col, val in filters.items():
                        conditions.append(QueryCondition(field=col, operator='eq', value=val))
                    req = SearchRequest(
                        object_type=meta_object.id,
                        conditions=conditions,
                        order_by=order_by,
                        page=page,
                        page_size=page_size,
                        skip_count=False,
                    )
                    result = qs.search(req)
                    logger.info(f"[_do_list] QueryService.search returned {len(result.data)} rows, total={result.total}")
                    if result.data:
                        try:
                            from meta.core.enrichment_engine import EnrichmentEngine
                            result.data = EnrichmentEngine.for_data_source(self.ds).enrich_fk_display_names(meta_object, result.data)
                        except Exception as e:
                            logger.warning(f"[_do_list] enrich_fk_display_names failed: {e}")
                    return ActionResult.ok(data=result.data)
                except Exception as e:
                    logger.error(f"[_do_list] QueryService.search routing failed: {e}, falling back to ds.find")

        try:
            records = self.ds.find(
                meta_object.table_name,
                filters=filters,
                order_by=order_by,
                limit=limit
            )

            logger.info(f"[_do_list] ds.find returned {len(records)} records")

            # 如果有offset，手动切片
            if offset and records:
                records = records[offset:]
                logger.info(f"[_do_list] after offset={offset}: {len(records)} records")

            try:
                with open(r'D:\filework\excel-to-diagram\logs\_dbg_do_list.log', 'a', encoding='utf-8') as f:
                    f.write(f"  ds.find returned {len(records)} records, filters={filters}\n")
            except Exception:
                pass

            return ActionResult.ok(data=records)
        except Exception as e:
            logger.error(f"[_do_list] Error: {e}")
            return ActionResult.fail(
                error="LIST_FAILED",
                message=str(e)
            )
    
    def _do_update(self, meta_object: MetaObject, params: Dict[str, Any],
                    skip_rules: bool = False) -> ActionResult:
        """执行更新操作"""
        id_value = params.get("id")
        if id_value is None:
            return ActionResult.fail(
                error="MISSING_ID",
                message="Parameter 'id' is required"
            )

        fields = meta_object.get_persistent_fields()
        data = self._prepare_data(fields, params, for_update=True)

        if not data:
            return ActionResult.fail(
                error="NO_DATA_TO_UPDATE",
                message="No valid fields to update"
            )

        try:
            data = self._resolve_foreign_keys(meta_object, data, params)
        except ValueError as e:
            return ActionResult.fail(
                error="FOREIGN_KEY_RESOLUTION_FAILED",
                message=str(e)
            )
        
        data = self._write_guard.on_before_save(meta_object.id, data)
        data = self._computed_field_handler.on_before_save(meta_object.id, data)

        original_data = None
        try:
            original_data = self.ds.find_by_id(meta_object.table_name, id_value)
        except:
            pass
        
        if original_data:
            hierarchy_result = validate_update(
                meta_object.id, original_data, data, self.ds
            )
            if not hierarchy_result.valid:
                return ActionResult.fail(
                    error=hierarchy_result.error_code,
                    message=hierarchy_result.message
                )
        
        if not skip_rules:
            merged_data = dict(original_data) if original_data else {}
            merged_data.update(data)
            validation_result = self._validate_before_update(
                meta_object, merged_data, original_data, exclude_id=id_value
            )
            if validation_result:
                return validation_result
            
            report = self.rule_engine.execute_rules(
                meta_object, RuleTrigger.BEFORE_UPDATE, data, original_data
            )
            if not report.success:
                result = ActionResult.fail(
                    error="VALIDATION_FAILED",
                    message="Before update validation failed"
                )
                result.rule_report = report
                return result

            report = self.rule_engine.execute_rules(
                meta_object, RuleTrigger.BEFORE_SAVE, data, original_data
            )
            if not report.success:
                result = ActionResult.fail(
                    error="VALIDATION_FAILED",
                    message="Before save validation failed"
                )
                result.rule_report = report
                return result

            data = self.rule_engine.compute(meta_object, data, original_data)
        
        try:
            version = params.get('version')
            with self.ds.transaction():
                if version is not None and hasattr(self.ds, 'update_with_version'):
                    self.ds.update_with_version(
                        meta_object.table_name, id_value, data,
                        expected_version=version
                    )
                else:
                    self.ds.update(meta_object.table_name, id_value, data)
                
                if not skip_rules:
                    data["id"] = id_value
                    self.rule_engine.execute_rules(
                        meta_object, RuleTrigger.AFTER_UPDATE, data, original_data
                    )
                    self.rule_engine.execute_rules(
                        meta_object, RuleTrigger.AFTER_SAVE, data, original_data
                    )
                
                if original_data:
                    changed_fields = {
                        k: v for k, v in data.items()
                        if original_data.get(k) != v
                    }
                    if changed_fields:
                        self._cascade_guard.on_after_update(
                            meta_object.id, id_value, changed_fields
                        )
                        self._trigger_aggregate_refresh(meta_object.id, id_value, "updated")
            
            if original_data:
                parent_type, parent_id = self._resolve_parent_info(meta_object, original_data)
                self._write_audit_log_v2(
                    lambda trace_id=None, transaction_id=None, user_id=None, user_name=None, ip_address=None, user_agent=None: self.audit_logger.log_update(
                        object_type=meta_object.id,
                        object_id=id_value,
                        old_data=original_data,
                        new_data=data,
                        trace_id=trace_id,
                        transaction_id=transaction_id,
                        parent_object_type=parent_type,
                        parent_object_id=parent_id,
                        user_id=user_id,
                        user_name=user_name,
                        ip_address=ip_address,
                        user_agent=user_agent
                    )
                )
            
            updated_data = self.ds.find_by_id(meta_object.table_name, id_value)
            
            result = ActionResult.ok(
                data=updated_data,
                message="{0} updated successfully".format(meta_object.name)
            )
            result.affected_rows = 1
            return result
        except ConcurrentModificationError as e:
            return ActionResult.fail(
                error="CONCURRENT_MODIFICATION",
                message=str(e)
            )
        except Exception as e:
            return ActionResult.fail(
                error="UPDATE_FAILED",
                message=translate_error_message(str(e), meta_object)
            )
    
    def _write_delete_blocked_audit(
        self,
        meta_object: MetaObject,
        id_value: Any,
        original_data: Optional[Dict[str, Any]],
        action_label: str,
        error_code: str,
        message: str,
    ) -> None:
        """[FIX 2026-06-12] 记录"删除被拒/失败"审计, 让审计链完整可追溯。

        当 delete 被 FK / restrict_on / deletability / 业务规则拦截, 或 SQL 异常时,
        写一条 action=DELETE_BLOCKED|DELETE_FAILED 审计, 保留原 record snapshot + 失败原因,
        便于排查"为什么没有 DELETE 审计"。

        审计失败不影响业务失败结果, 最多 warning 日志。
        """
        if not original_data:
            return
        try:
            parent_type, parent_id = self._resolve_parent_info(meta_object, original_data)
            self._write_audit_log_v2(
                lambda trace_id=None, transaction_id=None, user_id=None, user_name=None, ip_address=None, user_agent=None: self.audit_logger.log(
                    object_type=meta_object.id,
                    object_id=id_value,
                    action=action_label,
                    extra_data={
                        "blocked": True,
                        "error_code": error_code,
                        "message": message,
                        "record_snapshot": original_data,
                    },
                    trace_id=trace_id,
                    transaction_id=transaction_id,
                    parent_object_type=parent_type,
                    parent_object_id=parent_id,
                    user_id=user_id,
                    user_name=user_name,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            )
        except Exception as audit_err:
            logger.warning(
                "[Audit] Failed to write delete-blocked audit: %s", audit_err
            )

    def _do_delete(self, meta_object: MetaObject, params: Dict[str, Any],
                   skip_rules: bool = False) -> ActionResult:
        """执行删除操作"""
        id_value = params.get("id")
        if id_value is None:
            return ActionResult.fail(
                error="MISSING_ID",
                message="Parameter 'id' is required"
            )

        original_data = None
        try:
            original_data = self.ds.find_by_id(meta_object.table_name, id_value)
        except:
            pass

        if not original_data:
            obj_display = meta_object.name or meta_object.id
            return ActionResult.fail(
                error="NOT_FOUND",
                message=f"记录不存在: {obj_display}"
            )

        if original_data:
            hierarchy_result = validate_delete(
                meta_object.id, id_value, self.ds
            )
            if not hierarchy_result.valid:
                self._write_delete_blocked_audit(
                    meta_object, id_value, original_data,
                    action_label="DELETE_BLOCKED",
                    error_code=hierarchy_result.error_code or "HIERARCHY_BLOCKED",
                    message=hierarchy_result.message,
                )
                return ActionResult.fail(
                    error=hierarchy_result.error_code,
                    message=hierarchy_result.message
                )

        if not skip_rules and original_data:
            if not self._check_deletability(meta_object, original_data):
                msg = getattr(meta_object.deletability, 'message', None) or '该记录不可删除'
                self._write_delete_blocked_audit(
                    meta_object, id_value, original_data,
                    action_label="DELETE_BLOCKED",
                    error_code="CANNOT_DELETE",
                    message=msg,
                )
                return ActionResult.fail(
                    error="CANNOT_DELETE",
                    message=msg
                )

            ref_errors = self._check_reverse_fk_references(meta_object, id_value)
            if ref_errors:
                self._write_delete_blocked_audit(
                    meta_object, id_value, original_data,
                    action_label="DELETE_BLOCKED",
                    error_code="REFERENTIAL_INTEGRITY",
                    message="; ".join(ref_errors),
                )
                return ActionResult.fail(
                    error="REFERENTIAL_INTEGRITY",
                    message="; ".join(ref_errors)
                )

            restrict_errors = self._check_deletion_policy_restrict(meta_object, id_value)
            if restrict_errors:
                self._write_delete_blocked_audit(
                    meta_object, id_value, original_data,
                    action_label="DELETE_BLOCKED",
                    error_code="RESTRICT_ON_DELETE",
                    message="; ".join(restrict_errors),
                )
                return ActionResult.fail(
                    error="RESTRICT_ON_DELETE",
                    message="; ".join(restrict_errors)
                )

            report = self.rule_engine.execute_rules(
                meta_object, RuleTrigger.BEFORE_DELETE, original_data
            )
            if not report.success:
                self._write_delete_blocked_audit(
                    meta_object, id_value, original_data,
                    action_label="DELETE_BLOCKED",
                    error_code="VALIDATION_FAILED",
                    message="Before delete validation failed",
                )
                result = ActionResult.fail(
                    error="VALIDATION_FAILED",
                    message="Before delete validation failed"
                )
                result.rule_report = report
                return result

        try:
            self._cleanup_m2m_tables(meta_object, id_value)
            with self.ds.transaction():
                if meta_object.soft_delete:
                    delete_field = meta_object.soft_delete_field
                    delete_data = {delete_field: meta_object.soft_delete_value}

                    if hasattr(self.ds, 'update'):
                        self.ds.update(meta_object.table_name, id_value, delete_data)

                    if not skip_rules and original_data:
                        original_data[delete_field] = meta_object.soft_delete_value
                        self.rule_engine.execute_rules(
                            meta_object, RuleTrigger.AFTER_DELETE, original_data
                        )
                else:
                    try:
                        cursor = self.ds.execute(
                            f"DELETE FROM {meta_object.table_name} WHERE id = ?",
                            (id_value,)
                        )
                        if cursor is not None:
                            rowcount = getattr(cursor, 'rowcount', None)
                            if rowcount is not None and rowcount == 0:
                                obj_display = meta_object.name or meta_object.id
                                return ActionResult.fail(
                                    error="NOT_FOUND",
                                    message=f"记录不存在: {obj_display}"
                                )
                    except Exception as e:
                        # [FIX 2026-06-12] SQL DELETE 失败（典型：FK 违反）必须冒泡，
                        # 不能 silently 吞错 → 之前 bug：函数继续走 AFTER_DELETE + 审计 +
                        # 返回 ActionResult.ok，前端看到"成功"但记录未删（"没有成功，也没有报错"）
                        logger.warning(f"[_do_delete] DELETE execution error: {e}")
                        self._write_delete_blocked_audit(
                            meta_object, id_value, original_data,
                            action_label="DELETE_FAILED",
                            error_code="DELETE_FAILED",
                            message=f"删除失败（数据库约束）: {e}",
                        )
                        return ActionResult.fail(
                            error="DELETE_FAILED",
                            message=f"删除失败（数据库约束）: {e}",
                        )

                    if not skip_rules and original_data:
                        self.rule_engine.execute_rules(
                            meta_object, RuleTrigger.AFTER_DELETE, original_data
                        )

            if original_data:
                parent_type, parent_id = self._resolve_parent_info(meta_object, original_data)
                self._write_audit_log_v2(
                    lambda trace_id=None, transaction_id=None, user_id=None, user_name=None, ip_address=None, user_agent=None: self.audit_logger.log_delete(
                        object_type=meta_object.id,
                        object_id=id_value,
                        data=original_data,
                        trace_id=trace_id,
                        transaction_id=transaction_id,
                        parent_object_type=parent_type,
                        parent_object_id=parent_id,
                        user_id=user_id,
                        user_name=user_name,
                        ip_address=ip_address,
                        user_agent=user_agent
                    )
                )
                self._trigger_aggregate_refresh(meta_object.id, id_value, "deleted")

            result = ActionResult.ok(
                message="{0} deleted successfully".format(meta_object.name)
            )
            result.affected_rows = 1
            return result
        except Exception as e:
            self._write_delete_blocked_audit(
                meta_object, id_value, original_data,
                action_label="DELETE_FAILED",
                error_code="DELETE_FAILED",
                message=translate_error_message(str(e), meta_object),
            )
            return ActionResult.fail(
                error="DELETE_FAILED",
                message=translate_error_message(str(e), meta_object)
            )
    
    def _execute_batch(self, meta_object: MetaObject, action: MetaAction,
                       params: Dict[str, Any], skip_rules: bool = False) -> ActionResult:
        """执行批量操作"""
        action_name = action.id.lower()
        
        if "import" in action_name or "batch" in action_name:
            return self._do_batch_insert(meta_object, params)
        elif "export" in action_name:
            return self._do_export(meta_object, params)
        else:
            return ActionResult.fail(
                error="UNSUPPORTED_BATCH_ACTION",
                message="Batch action '{0}' is not supported".format(action.id)
            )
    
    def _write_audit_log_v2(self, audit_fn):
        """V2 审计日志写入 — 参考 SAP V2 Update 模式

        业务事务提交后，审计日志通过 AsyncAuditWriter 异步写入。
        审计写入失败不影响业务结果，仅记录 warning 日志。
        自动从 Flask g 对象获取 trace_id / transaction_id / 用户上下文。

        测试环境下完全跳过审计日志写入（避免 audit_logs 表缺失导致的测试失败）。
        """
        try:
            import os
            if os.environ.get('TESTING', '').lower() in ('true', '1', 'yes'):
                logger.debug("[AuditLog] Skipping audit log write in TESTING mode")
                return

            trace_id = None
            transaction_id = None
            user_id = None
            user_name = None
            ip_address = None
            user_agent = None
            try:
                from flask import g, request
                trace_id = getattr(g, 'trace_id', None)
                transaction_id = getattr(g, 'transaction_id', None)
                # [FIX 2026-06-19] 业务人员看不到完整操作的根因: 62% 日志无 tx/trace
                # 这里自动生成, 即使 Flask g context 没有也能让所有 audit_log 归组
                if not transaction_id:
                    transaction_id = f"tx_{uuid.uuid4().hex[:16]}"
                    try:
                        g.transaction_id = transaction_id
                    except Exception:
                        pass
                if not trace_id:
                    trace_id = f"tr_{uuid.uuid4().hex[:16]}"
                    try:
                        g.trace_id = trace_id
                    except Exception:
                        pass
                # [FIX Bug3 2026-06-09] 显式从 g.current_user 读取用户信息，
                # 避免异步执行时 audit_logger._current_user 已被重置/被覆盖
                current_user = getattr(g, 'current_user', None)
                if isinstance(current_user, dict):
                    user_id = current_user.get('user_id') or current_user.get('id')
                    user_name = current_user.get('display_name') or current_user.get('username')
                try:
                    if request is not None:
                        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
                        if ip_address and ',' in ip_address:
                            ip_address = ip_address.split(',')[0].strip()
                        user_agent = request.headers.get('User-Agent', '')
                except RuntimeError:
                    pass
            except (ImportError, RuntimeError):
                pass

            from meta.services.async_audit_writer import async_audit_writer, AUDIT_ASYNC_ENABLED
            # [FIX 2026-06-18] 事务期间强制同步写入:
            # 当 self.ds.in_transaction=True 时, 不能用 async_audit_writer.
            # 原因: async_audit_writer 用 worker thread + 独立 SQLite 连接
            # 写 audit_logs, 这部分写入不在主事务范围内, 主事务 rollback
            # 时 audit log 不会跟着回滚, 导致业务回滚但审计仍然存在
            # (例如用户报告: TEST111 + 2 个同名 version, 失败时第 1 个
            # version 的 audit log 仍然落库, 不符合 all-or-nothing).
            # 事务内直接同步调用 audit_fn, 让 audit insert 加入当前
            # 事务, 共享 commit/rollback 生命周期.
            in_txn = False
            try:
                in_txn = bool(getattr(self.ds, 'in_transaction', False))
            except Exception:
                in_txn = False
            if in_txn:
                logger.debug(
                    "[AuditLog] In transaction, writing audit synchronously "
                    "(txn_id=%s) to ensure atomicity with business data",
                    transaction_id,
                )
                try:
                    audit_fn(
                        trace_id=trace_id,
                        transaction_id=transaction_id,
                        user_id=user_id,
                        user_name=user_name,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                except Exception as e:
                    logger.warning(
                        "[AuditLog] sync write inside transaction failed (will NOT fail business): %s",
                        str(e),
                    )
            elif AUDIT_ASYNC_ENABLED and async_audit_writer._ds is not None:
                async_audit_writer.submit(
                    audit_fn,
                    trace_id=trace_id,
                    transaction_id=transaction_id,
                    user_id=user_id,
                    user_name=user_name,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            else:
                with self.ds.transaction():
                    audit_fn(
                        trace_id=trace_id,
                        transaction_id=transaction_id,
                        user_id=user_id,
                        user_name=user_name,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
        except Exception as e:
            logger.warning("Audit log V2 write failed: %s", str(e))
    
    def _do_batch_insert(self, meta_object: MetaObject, 
                         params: Dict[str, Any]) -> ActionResult:
        """批量插入"""
        data_list = params.get("data", params.get("items", []))
        
        if not data_list:
            return ActionResult.fail(
                error="NO_DATA",
                message="No data provided for batch insert"
            )
        
        fields = meta_object.get_persistent_fields()
        prepared_list = []
        
        for item in data_list:
            data = self._prepare_data(fields, item, for_create=True)
            if data:
                prepared_list.append(data)
        
        if not prepared_list:
            return ActionResult.fail(
                error="NO_VALID_DATA",
                message="No valid data to insert"
            )
        
        try:
            count = self.ds.batch_insert(meta_object.table_name, prepared_list)
            result = ActionResult.ok(
                data={"inserted_count": count},
                message="Successfully inserted {0} records".format(count)
            )
            result.affected_rows = count
            
            self._write_audit_log_v2(
                lambda trace_id=None, transaction_id=None, user_id=None, user_name=None, ip_address=None, user_agent=None: self.audit_logger.log_create(
                    object_type=meta_object.id,
                    object_id=0,
                    data={'batch_inserted_count': count, 'object_type': meta_object.id},
                    trace_id=trace_id,
                    transaction_id=transaction_id,
                    user_id=user_id,
                    user_name=user_name,
                    ip_address=ip_address,
                    user_agent=user_agent
                )
            )
            
            return result
        except Exception as e:
            return ActionResult.fail(
                error="BATCH_INSERT_FAILED",
                message=str(e)
            )
    
    def _do_export(self, meta_object: MetaObject, 
                   params: Dict[str, Any]) -> ActionResult:
        """导出数据"""
        filters = params.get("filters", {})
        
        try:
            records = self.ds.find(meta_object.table_name, filters=filters)
            return ActionResult.ok(
                data=records,
                message="Exported {0} records".format(len(records))
            )
        except Exception as e:
            return ActionResult.fail(
                error="EXPORT_FAILED",
                message=str(e)
            )
    
    def _execute_business(self, meta_object: MetaObject, action: MetaAction,
                          params: Dict[str, Any]) -> ActionResult:
        """执行业务操作 - 支持声明式 behavior 配置"""
        if action.behavior:
            return self._execute_declarative_business(meta_object, action, params)

        return ActionResult.fail(
            error="BUSINESS_ACTION_NOT_IMPLEMENTED",
            message="Business action '{0}' needs custom implementation".format(action.id)
        )

    def _execute_declarative_business(self, meta_object: MetaObject,
                                       action: MetaAction,
                                       params: Dict[str, Any]) -> ActionResult:
        """执行声明式业务操作"""
        from meta.core.condition_evaluator import ConditionEvaluator

        if action.behavior.precondition:
            pc = action.behavior.precondition
            record_id = params.get("id")
            record = {}
            if record_id:
                try:
                    record = self.ds.find_by_id(meta_object.table_name, record_id) or {}
                except Exception:
                    pass

            context = {"self": record, "parameters": params}
            evaluator = ConditionEvaluator()
            can_execute, msg = evaluator.evaluate_with_message(
                pc.condition,
                pc.message or "前置条件不满足",
                context=context,
            )
            if not can_execute:
                return ActionResult.fail(
                    error="PRECONDITION_FAILED",
                    message=msg,
                )

        if not action.behavior.effects:
            return ActionResult.ok(
                data=params,
                message="Action '{0}' executed (no effects)".format(action.id),
            )

        record_id = params.get("id")
        if not record_id:
            return ActionResult.fail(
                error="MISSING_ID",
                message="Business action requires 'id' parameter",
            )

        record = None
        try:
            record = self.ds.find_by_id(meta_object.table_name, record_id)
        except Exception:
            pass

        if not record:
            return ActionResult.fail(
                error="NOT_FOUND",
                message="{0} with id={1} not found".format(meta_object.name, record_id),
            )

        for effect in action.behavior.effects:
            if effect.type == "set_fields":
                result = self._apply_set_fields_effect(
                    meta_object, record, record_id, effect, params
                )
                if not result.success:
                    return result
                record = result.data or record
            elif effect.type == "trigger":
                if effect.handler:
                    try:
                        handler_func = self._resolve_handler(effect.handler)
                        if handler_func:
                            handler_func(meta_object, record, params, self.ds)
                    except Exception as e:
                        logger.warning("Handler '%s' failed: %s", effect.handler, e)

        updated_record = None
        try:
            updated_record = self.ds.find_by_id(meta_object.table_name, record_id)
        except Exception:
            pass

        return ActionResult.ok(
            data=updated_record or record,
            message="Action '{0}' executed successfully".format(action.id),
        )

    def _apply_set_fields_effect(self, meta_object: MetaObject,
                                  record: Dict[str, Any],
                                  record_id: Any,
                                  effect: "ActionEffect",
                                  params: Dict[str, Any]) -> ActionResult:
        """应用 set_fields 效果

        [FIX 2026-06-12] 审计合规修复:
        - 之前: self.ds.update(table, id, data) → 走 raw SQL, 绕过 audit_logs
        - 现在: 通过 BOFramework.update() 走完整拦截器链
          (PermissionInterceptor → DataPermissionInterceptor → CascadeInterceptor →
           AuditInterceptor → BusinessLogInterceptor → PersistenceInterceptor →
           ActionRegistry.update → ActionExecutor.execute('crud_update') →
           ActionExecutor._do_update → _write_audit_log_v2 → audit_logs 表)

        这样 business action 的 set_fields 效果也能产生 audit log,
        比如 set_current action 把 is_current=true 写到自己身上也会有审计记录。

        - 同时, audit_aspect 的 auto_fill (created_by/updated_by) 也会被填充
        - 兜底: 如果 BOFramework.update() 失败 (例如 bo_framework 不可用), 回退到 raw SQL
          (保留旧行为, 不阻塞 action 流程)
        """
        update_data = {}
        for field_name, field_value in effect.fields.items():
            resolved_value = self._resolve_field_value(field_value, record, params)
            field = meta_object.get_field(field_name)
            db_col = field.db_column if field else field_name
            update_data[db_col] = resolved_value

        if not update_data:
            return ActionResult.ok(data=record)

        # 1) 优先走 BOFramework.update() 触发 audit log
        try:
            from meta.core.bo_framework import bo_framework as _bo

            # 同步 user context (从 Flask g.current_user / executor._request_context)
            self._sync_user_context_for_business_action()

            bo_result = _bo.update(meta_object.id, record_id, update_data)
            if bo_result and bo_result.success:
                # 用更新后的 record (bo_result.data 包含新值) 刷新本地 record
                if isinstance(bo_result.data, dict):
                    record.update(bo_result.data)
                else:
                    record.update(update_data)
                return ActionResult.ok(
                    data=record,
                    message=bo_result.message or "set_fields effect applied via BO framework",
                )
            else:
                # BO framework 失败 (例如权限被拒) - 不再静默回退到 raw SQL, 因为
                # 那会导致 audit 不一致 (raw SQL 没 audit log, 但业务上字段已写？)
                # 实际上 _bo.update() 在 permission denied 时也会 fail 不写, 所以失败
                # 是合理的, 应当冒泡
                logger.warning(
                    f"[set_fields_effect] BOFramework.update failed for "
                    f"{meta_object.id}#{record_id}: {bo_result.message if bo_result else 'No result'}"
                )
                return ActionResult.fail(
                    error=bo_result.error if bo_result else "SET_FIELDS_FAILED",
                    message=bo_result.message if bo_result else "BO framework update failed",
                )
        except Exception as e:
            # [FIX 2026-06-12] BO framework 不可用 / 异常时, 不再 fallback raw SQL
            # (raw SQL 会让 audit 与业务不一致). 直接报错让 caller 处理.
            # 唯一例外: 当 bo_framework 真的 import 失败 (例如单元测试环境),
            # 才走 raw SQL 兜底, 保持向后兼容.
            error_msg = str(e)
            is_bootstrap_failure = (
                'ImportError' in error_msg
                or 'cannot import' in error_msg
                or 'bo_framework' in error_msg
                or isinstance(e, ImportError)
            )
            if is_bootstrap_failure:
                logger.warning(
                    f"[set_fields_effect] BOFramework not available ({e}), "
                    f"falling back to raw SQL (no audit log)"
                )
                try:
                    self.ds.update(meta_object.table_name, record_id, update_data)
                    record.update(update_data)
                    return ActionResult.ok(data=record)
                except Exception as inner_e:
                    return ActionResult.fail(
                        error="SET_FIELDS_FAILED",
                        message=str(inner_e),
                    )
            # 其他异常 (运行时错误) 应当冒泡
            return ActionResult.fail(
                error="SET_FIELDS_FAILED",
                message=f"BOFramework.update raised: {e}",
            )

    def _sync_user_context_for_business_action(self) -> None:
        """[FIX 2026-06-12] business action 调 BOFramework.update() 前同步 user context.

        ActionExecutor 自己的 audit_logger._current_user 是独立的属性, 跟 BOFramework
        _user_context 无关。set_current action 处理过程中, audit_logger 可能没设 user,
        导致 BOFramework.update() 内部的 audit log 写时 user_id/user_name 为空。

        同步策略:
          1) 从 Flask g.current_user (auth_middleware 已设) 拿 user_id/user_name/ip
          2) 写到 bo_framework._user_context (走 set_user_context)
          3) 找到 PersistenceInterceptor._registry.executor, 调 set_audit_user()
             (同时写 audit_logger._current_user + _pseudo_resolver._user_context)
        """
        try:
            from flask import g, request
            from meta.core.bo_framework import bo_framework as _bo
            from meta.services.auth_middleware import get_current_user

            current_user = (
                get_current_user()
                or getattr(g, 'current_user', None)
                or self._request_context.get('user')
                or {}
            )
            if not current_user:
                return

            user_id = current_user.get('user_id') or current_user.get('id')
            display = current_user.get('display_name') or ''
            username = current_user.get('username') or ''
            # [FIX 2026-06-19 D.2 v3] 优先用 display_name, 不要拼接 "display (username)"
            # 之前 "Admin (admin)" 业务人员看不懂, 现在统一只用 display_name
            user_name = display or username or ''
            try:
                ip_address = request.remote_addr
            except RuntimeError:
                ip_address = ''
            try:
                user_agent = request.headers.get('User-Agent', '')
            except RuntimeError:
                user_agent = ''

            _bo.set_user_context(
                user_id=user_id,
                user_name=user_name,
                ip_address=ip_address,
            )

            for interceptor in getattr(_bo, 'interceptors', []) or []:
                cls_name = interceptor.__class__.__name__
                if cls_name != 'PersistenceInterceptor':
                    continue
                registry = getattr(interceptor, '_registry', None)
                if registry is None:
                    continue
                executor = getattr(registry, 'executor', None)
                if executor is None:
                    continue
                if hasattr(executor, 'set_audit_user'):
                    executor.set_audit_user(
                        user_id=user_id,
                        user_name=user_name,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                break
        except Exception as e:
            logger.debug(f"[set_fields_effect] User context sync skipped: {e}")

    def _resolve_field_value(self, expression: Any, record: Dict[str, Any],
                              params: Dict[str, Any]) -> Any:
        """解析字段值表达式，支持伪变量"""
        if not isinstance(expression, str):
            return expression

        if expression == "$now":
            return datetime.now().isoformat()
        elif expression == "$user.id":
            return self._pseudo_resolver._user_context.get("user_id", "")
        elif expression == "$user.name":
            return self._pseudo_resolver._user_context.get("user_name", "")
        elif expression == "$uuid":
            import uuid
            return str(uuid.uuid4())
        elif expression.startswith("$parameters."):
            param_name = expression[len("$parameters."):]
            return params.get(param_name, expression)
        elif expression.startswith("$self."):
            field_name = expression[len("$self."):]
            return record.get(field_name, expression)
        else:
            return expression

    def _resolve_handler(self, handler_path: str):
        """解析 handler 函数路径"""
        try:
            parts = handler_path.rsplit(".", 1)
            if len(parts) == 2:
                module_path, func_name = parts
                import importlib
                module = importlib.import_module(module_path)
                return getattr(module, func_name, None)
        except Exception:
            pass
        return None
    
    def _compute_hierarchy_path(self, meta_object: MetaObject, data: Dict[str, Any], 
                                 params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        计算层级路径
        
        如果对象有层级路径字段，自动计算并填充
        """
        hierarchy_field = meta_object.get_hierarchy_path_field()
        if not hierarchy_field:
            return data
        
        separator = hierarchy_field.hierarchy_separator or "/"
        params = params or {}
        
        path_parts = []
        
        if meta_object.parent_object:
            parent_id_field = "{0}_id".format(meta_object.parent_object)
            parent_id = data.get(parent_id_field) or params.get(parent_id_field)
            
            if parent_id:
                try:
                    from meta import get_meta_object
                    parent_meta = get_meta_object(meta_object.parent_object)
                    if parent_meta:
                        parent_record = self.ds.find_by_id(parent_meta.table_name, parent_id)
                        if parent_record:
                            parent_path_field = parent_meta.get_hierarchy_path_field()
                            if parent_path_field and parent_path_field.db_column in parent_record:
                                path_parts.append(parent_record[parent_path_field.db_column])
                            else:
                                path_parts.append(str(parent_id))
                except:
                    path_parts.append(str(parent_id))
        
        obj_id = data.get("id") or data.get("name", "")
        if obj_id:
            path_parts.append(str(obj_id))
        
        if path_parts:
            data[hierarchy_field.db_column] = separator.join(path_parts)
        
        depth_field = None
        for f in meta_object.fields:
            if f.id == "hierarchy_depth":
                depth_field = f
                break
        
        if depth_field:
            data[depth_field.db_column] = len(path_parts) - 1 if path_parts else 0
        
        return data
    
    def _prepare_data(self, fields: List[MetaField], params: Dict[str, Any],
                      for_create: bool = False, for_update: bool = False) -> Optional[Dict[str, Any]]:
        data = {}

        for field in fields:
            if field.id == "id" and for_create:
                continue

            if for_update and hasattr(field, 'semantics') and field.semantics.readonly_always:
                continue

            if for_update and hasattr(field, 'permission') and field.permission and not field.permission.writable:
                continue

            if field.id in params:
                value = self._convert_value(params[field.id], field)
                data[field.db_column] = value
            elif for_create and field.default is not None:
                data[field.db_column] = field.default

        if for_create or for_update:
            for field in fields:
                auto_fill = field.semantics.auto_fill if hasattr(field.semantics, 'auto_fill') else {}
                if auto_fill:
                    if for_create and 'on_create' in auto_fill:
                        value = self._pseudo_resolver.resolve(auto_fill['on_create'])
                        data[field.db_column] = value
                    elif for_update and 'on_update' in auto_fill:
                        value = self._pseudo_resolver.resolve(auto_fill['on_update'])
                        data[field.db_column] = value
                else:
                    if for_create and field.id == 'created_at' and field.db_column not in data:
                        data[field.db_column] = datetime.now().isoformat()
                    # updated_at 不再物理存储：SSOT 从 audit_logs 实时计算
                    # (aspects.yaml: storage=virtual, materialization.strategy=virtual)

            if for_create and self._request_context:
                for field in fields:
                    if (hasattr(field, 'semantics') and field.semantics.context_field
                            and field.db_column not in data and field.id in self._request_context):
                        data[field.db_column] = self._convert_value(
                            self._request_context[field.id], field
                        )

        return data if data else None
    
    def _convert_value(self, value: Any, field: MetaField) -> Any:
        """类型转换"""
        if value is None:
            return None
        
        try:
            if field.field_type == FieldType.INTEGER:
                return int(value)
            elif field.field_type == FieldType.FLOAT:
                return float(value)
            elif field.field_type == FieldType.BOOLEAN:
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes")
                return bool(value)
            elif field.field_type == FieldType.DATETIME:
                if isinstance(value, str):
                    return value
                elif isinstance(value, datetime):
                    return value.isoformat()
            return value
        except (ValueError, TypeError):
            return value
    
    def _trigger_aggregate_refresh(self, object_type: str, object_id: Any, event_type: str):
        """触发聚合刷新（非阻塞，失败仅记录日志）"""
        try:
            from meta.core.aggregate_manager import get_aggregate_manager
            from meta.core.aggregate_refresh_handler import AggregateRefreshHandler
            
            manager = get_aggregate_manager()
            if not manager:
                return
            
            handler = AggregateRefreshHandler(manager)
            handler.on_data_changed(object_type, object_id, event_type)
        except Exception as e:
            logger.debug(
                "Aggregate refresh skipped: object_type=%s, object_id=%s, error=%s",
                object_type, object_id, str(e)
            )


class ActionRegistry:
    """
    Action 注册表 - 管理所有 Action 执行器
    """
    
    def __init__(self, data_source: DataSource, rule_engine=None):
        self.ds = data_source
        self.executor = ActionExecutor(data_source, rule_engine)
        self._custom_handlers: Dict[str, callable] = {}
    
    def register_handler(self, action_key: str, handler: callable) -> None:
        """
        注册自定义 Action 处理器
        
        Args:
            action_key: 格式为 "object_id:action_id"，如 "product:custom_action"
            handler: 处理函数，签名为 (meta_object, action, params) -> ActionResult
        """
        self._custom_handlers[action_key] = handler
    
    def execute(self, meta_object: MetaObject, action_id: str,
                params: Optional[Dict[str, Any]] = None,
                skip_rules: bool = False) -> ActionResult:
        """执行 Action，支持自定义处理器"""
        action_key = "{0}:{1}".format(meta_object.id, action_id)
        
        if action_key in self._custom_handlers:
            action = meta_object.get_action(action_id)
            if action:
                return self._custom_handlers[action_key](meta_object, action, params or {})
        
        resolved_id = action_id
        if not meta_object.get_action(action_id) and action_id.startswith('crud_'):
            suffix = action_id[5:]
            alt_id = "{0}_{1}".format(meta_object.id, suffix)
            if meta_object.get_action(alt_id):
                resolved_id = alt_id
        
        return self.executor.execute(meta_object, resolved_id, params, skip_rules)
    
    def create(self, meta_object: MetaObject, data: Dict[str, Any]) -> ActionResult:
        """便捷方法：创建记录"""
        return self.execute(meta_object, "crud_create", data)
    
    def read(self, meta_object: MetaObject, id_value: Any) -> ActionResult:
        """便捷方法：读取单条"""
        return self.execute(meta_object, "crud_read", {"id": id_value})
    
    def list(self, meta_object: MetaObject, filters: Optional[Dict[str, Any]] = None) -> ActionResult:
        """便捷方法：列表查询"""
        return self.execute(meta_object, "crud_list", filters or {})
    
    def update(self, meta_object: MetaObject, id_value: Any, data: Dict[str, Any]) -> ActionResult:
        """便捷方法：更新记录"""
        params = {"id": id_value}
        params.update(data)
        return self.execute(meta_object, "crud_update", params)
    
    def delete(self, meta_object: MetaObject, id_value: Any) -> ActionResult:
        """便捷方法：删除记录"""
        return self.execute(meta_object, "crud_delete", {"id": id_value})
    
    def query(self, meta_object: MetaObject) -> QueryBuilder:
        """
        创建 QueryBuilder 进行灵活查询
        
        Returns:
            QueryBuilder 实例
            
        示例:
            results = registry.query(product) \\
                .where_like('name', '%供应链%') \\
                .where_eq('is_active', True) \\
                .order_by('created_at', 'desc') \\
                .page(1, 20) \\
                .execute()
        """
        return QueryBuilder(self.ds, meta_object)
    
    def execute_query(self, meta_object: MetaObject, query_id: str,
                      params: Optional[Dict[str, Any]] = None) -> ActionResult:
        """
        执行元模型中定义的查询模板
        
        Args:
            meta_object: 元模型对象
            query_id: 查询模板ID
            params: 参数值
            
        Returns:
            ActionResult
        """
        query_def = meta_object.get_query(query_id)
        if not query_def:
            return ActionResult.fail(
                error="QUERY_NOT_FOUND",
                message="Query '{0}' not found in '{1}'".format(query_id, meta_object.id)
            )
        
        try:
            builder = QueryBuilder(self.ds, meta_object).from_query(query_def, params)
            results = builder.execute()
            return ActionResult.ok(
                data=results,
                message="Query executed successfully"
            )
        except Exception as e:
            return ActionResult.fail(
                error="QUERY_FAILED",
                message=str(e)
            )
    
    def paginate(self, meta_object: MetaObject, page: int = 1, 
                 page_size: int = 20, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        分页查询便捷方法
        
        Args:
            meta_object: 元模型对象
            page: 页码（从1开始）
            page_size: 每页数量
            filters: 过滤条件
            
        Returns:
            分页结果
        """
        builder = QueryBuilder(self.ds, meta_object)
        
        if filters:
            for field, value in filters.items():
                if field.startswith("_"):
                    continue
                builder.where_eq(field, value)
        
        return builder.paginate(page, page_size)
