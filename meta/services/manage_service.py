from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import logging

from meta.core.action_executor import ActionExecutor, ActionResult
from meta.core.models import MetaObject, registry
from meta.core.datasource import DataSource
from meta.core.rule_executor import RuleEngine
from meta.core.condition_evaluator import ConditionEvaluator
from meta.services.change_notification_service import (
    ChangeNotificationService,
    ChangeEventRequest
)

logger = logging.getLogger(__name__)


@dataclass
class CreateRequest:
    object_type: str
    data: Dict[str, Any]
    skip_validation: bool = False
    skip_audit: bool = False


@dataclass
class UpdateRequest:
    object_type: str
    id: Any
    data: Dict[str, Any]
    skip_validation: bool = False
    skip_audit: bool = False


@dataclass
class DeleteRequest:
    object_type: str
    id: Any
    force: bool = False
    cascade: bool = False


@dataclass
class BatchOperationResult:
    success_count: int = 0
    failed_count: int = 0
    results: List[ActionResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class ManageService:

    def __init__(self, data_source: DataSource, rule_engine: Optional[RuleEngine] = None):
        self.data_source = data_source
        self.rule_engine = rule_engine or RuleEngine(data_source)
        self.executor = ActionExecutor(data_source, self.rule_engine)
        self.notification_service = ChangeNotificationService(data_source)

    def set_audit_user(self, user_id: Any = None, user_name: str = "",
                       ip_address: str = "", user_agent: str = "") -> None:
        self.executor.set_audit_user(user_id, user_name, ip_address, user_agent)

    def set_agent_context(self, agent_id: str = None, agent_session_id: str = None,
                          tool_call_id: str = None, agent_reasoning: str = None) -> None:
        self.executor.set_agent_context(agent_id, agent_session_id, tool_call_id, agent_reasoning)

    def _get_meta_object(self, object_type: str) -> MetaObject:
        meta_obj = registry.get(object_type)
        if meta_obj is None:
            raise ValueError("Meta object not found: {0}".format(object_type))
        return meta_obj

    def _get_latest_audit_log_id(self, object_type: str, object_id: Any) -> Optional[int]:
        """获取最近的审计日志ID"""
        try:
            logs = self.data_source.find(
                "audit_logs",
                filters={"object_type": object_type, "object_id": str(object_id)},
                order_by="id DESC",
                limit=1
            )
            if logs:
                return logs[0].get("id")
        except Exception as e:
            logger.warning("Failed to get audit log id: %s", str(e))
        return None

    def _write_cascade_audit_logs(self, parent_object_type: str, parent_object_id: Any,
                                   children_audit_info: list) -> None:
        """为级联删除的 composition children 写入审计日志"""
        try:
            from flask import g
            
            trace_id = getattr(g, 'trace_id', None)
            transaction_id = getattr(g, 'transaction_id', None)
            user_id = getattr(g, 'user_id', None)
            user_name = getattr(g, 'user_name', None)
            
            def write_batch():
                for child_info in children_audit_info:
                    self.executor.audit_logger.audit_service.log(
                        object_type=child_info['object_type'],
                        object_id=child_info['object_id'],
                        action='DELETE',
                        old_data=child_info.get('old_data', {}),
                        parent_object_type=child_info.get('parent_object_type'),
                        parent_object_id=child_info.get('parent_object_id'),
                        user_id=user_id,
                        user_name=user_name,
                        trace_id=trace_id,
                        transaction_id=transaction_id,
                    )
            
            self.executor._write_audit_log_v2(
                lambda trace_id=None, transaction_id=None: write_batch()
            )
        except Exception as e:
            logger.warning("Failed to write cascade audit logs: %s", str(e))

    def _publish_change_event(
        self,
        object_type: str,
        object_id: Any,
        event_type: str,
        old_data: Optional[Dict[str, Any]] = None,
        new_data: Optional[Dict[str, Any]] = None,
        audit_log_id: Optional[int] = None
    ) -> None:
        """发布变更事件（不阻塞主事务，失败时仅记录日志）"""
        try:
            request = ChangeEventRequest(
                object_type=object_type,
                object_id=object_id,
                event_type=event_type,
                old_data=old_data,
                new_data=new_data,
                audit_log_id=audit_log_id
            )
            result = self.notification_service.publish_event(request)
            if result.success:
                logger.debug(
                    "Change event published: object_type=%s, object_id=%s, event_type=%s",
                    object_type, object_id, event_type
                )
            else:
                logger.warning(
                    "Failed to publish change event: %s", result.message
                )
        except Exception as e:
            logger.error(
                "Exception while publishing change event: %s", str(e), exc_info=True
            )

    def _validate_value_helps(self, meta_obj: MetaObject, data: Dict[str, Any]) -> List[str]:
        """验证启用了 value_help.validation 的字段值是否有效

        [FR-007] 使用 value_help_accessor.get_value_help 统一获取 value_help，
        兼容 field.value_help 和 field.ui.value_help 两种定义方式。
        """
        from meta.core.value_help_accessor import get_value_help as _get_vh

        errors = []
        for field in meta_obj.fields:
            vh = _get_vh(field)
            if not vh:
                continue
            if not vh.validation:
                continue
            field_value = data.get(field.id)
            if field_value is None or field_value == "":
                continue
            # 获取关联对象信息：优先 field.ui.relation，其次从 vh.source 解析
            relation_meta = None
            if field.ui and field.ui.relation:
                relation_meta = registry.get(field.ui.relation)
            elif vh.source and getattr(vh.source, 'type', None) == 'bo':
                target_bo = getattr(vh.source, 'target_bo', None)
                if target_bo:
                    relation_meta = registry.get(target_bo)
            if not relation_meta:
                continue
            display_field = (field.ui.display_field if field.ui else None) or "name"
            try:
                filter_dict = {"id": field_value}
                records = self.data_source.find(relation_meta.table_name, filters=filter_dict)
                if not records:
                    msg = vh.validation_message or f"字段 {field.name} 的值 '{field_value}' 不在有效选项中"
                    errors.append(msg)
            except Exception as e:
                errors.append(f"验证字段 {field.name} 时出错: {str(e)}")
        return errors

    def _resolve_parent_context(self, meta_obj: MetaObject, data: Dict[str, Any]) -> Dict[str, Any]:
        parent_data = {}
        if meta_obj.parent_object:
            parent_meta = registry.get(meta_obj.parent_object)
            if parent_meta:
                parent_fk = None
                for f in meta_obj.fields:
                    if f.semantics.parent_key and f.semantics.context_field:
                        parent_fk = data.get(f.id)
                        break
                if not parent_fk:
                    for f in meta_obj.fields:
                        if f.semantics.parent_key:
                            parent_fk = data.get(f.id)
                            break
                if parent_fk:
                    try:
                        record = self.data_source.find_by_id(parent_meta.table_name, parent_fk)
                        if record:
                            parent_data = record
                    except Exception:
                        pass
        return parent_data

    def check_can_delete(self, object_type: str, record: Dict[str, Any]) -> bool:
        meta_obj = registry.get(object_type)
        if not meta_obj or not meta_obj.deletability or not meta_obj.deletability.condition:
            return True
        evaluator = ConditionEvaluator()
        can_delete = evaluator.evaluate(meta_obj.deletability.condition, context={"self": record})

        if not can_delete:
            return False

        from meta.core.models import RelationType

        for relation in meta_obj.relations:
            if relation.relation_type == RelationType.COMPOSITION and not relation.cascade_delete:
                child_meta = registry.get(relation.target_object)
                if child_meta:
                    fk_field = relation.source_field or f"{object_type}_id"
                    try:
                        child_records = self.data_source.find(
                            child_meta.table_name, {fk_field: record.get('id')}
                        )
                        if child_records:
                            return False
                    except Exception:
                        pass

        try:
            from meta.services.cascade_service import CascadeService
            cascade_svc = CascadeService(self.data_source)
            before_result = cascade_svc.before_delete(object_type, record.get('id'))
            if not before_result.get("can_delete", True):
                return False
        except Exception:
            pass

        return True

    def batch_check_can_delete(self, object_type: str, items: list) -> Dict[Any, bool]:
        meta_obj = registry.get(object_type)
        if not meta_obj or not meta_obj.deletability or not meta_obj.deletability.condition:
            return {item.get('id'): True for item in items if isinstance(item, dict)}

        evaluator = ConditionEvaluator()
        result = {}

        composition_relations = []
        if hasattr(meta_obj, 'relations') and meta_obj.relations:
            from meta.core.models import RelationType
            composition_relations = [
                r for r in meta_obj.relations
                if r.relation_type == RelationType.COMPOSITION and not r.cascade_delete
            ]

        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = item.get('id')
            can_delete = evaluator.evaluate(meta_obj.deletability.condition, context={"self": item})
            result[item_id] = can_delete

        if composition_relations:
            all_ids = list(result.keys())
            for relation in composition_relations:
                child_meta = registry.get(relation.target_object)
                if not child_meta:
                    continue
                fk_field = relation.source_field or f"{object_type}_id"
                try:
                    placeholders = ','.join(['?'] * len(all_ids))
                    sql = f"SELECT DISTINCT {fk_field} FROM {child_meta.table_name} WHERE {fk_field} IN ({placeholders})"
                    cursor = self.data_source.execute(sql, all_ids)
                    parent_ids_with_children = {row[0] for row in cursor.fetchall()}
                    for pid in parent_ids_with_children:
                        if pid in result:
                            result[pid] = False
                except Exception:
                    pass

        try:
            from meta.services.cascade_service import CascadeService
            cascade_svc = CascadeService(self.data_source)
            for item_id in all_ids:
                if not result.get(item_id, True):
                    continue
                try:
                    before_result = cascade_svc.before_delete(object_type, item_id)
                    if not before_result.get("can_delete", True):
                        result[item_id] = False
                except Exception:
                    pass
        except Exception:
            pass

        return result

    def check_can_add(self, object_type: str, data: Dict[str, Any] = None) -> bool:
        meta_obj = registry.get(object_type)
        if not meta_obj or not meta_obj.addability or not meta_obj.addability.condition:
            return True
        evaluator = ConditionEvaluator()
        parent_data = self._resolve_parent_context(meta_obj, data or {})
        context = {"self": data or {}, "parent": parent_data}
        return evaluator.evaluate(meta_obj.addability.condition, context=context)

    def create(self, request: CreateRequest) -> ActionResult:
        logger.info(f"[ManageService] create: object_type={request.object_type}")
        logger.info(f"[ManageService] data keys: {list(request.data.keys())}")
        logger.info(f"[ManageService] version_id in data: {request.data.get('version_id')}")

        meta_obj = self._get_meta_object(request.object_type)

        if meta_obj.addability and meta_obj.addability.condition:
            evaluator = ConditionEvaluator()
            parent_data = self._resolve_parent_context(meta_obj, request.data)
            context = {"self": request.data, "parent": parent_data}
            can_add, msg = evaluator.evaluate_with_message(
                meta_obj.addability.condition,
                meta_obj.addability.message or "当前条件不允许新增",
                context=context,
            )
            if not can_add:
                return ActionResult.fail(error="ADDABILITY_DENIED", message=msg)

        validation_errors = self._validate_value_helps(meta_obj, request.data)
        if validation_errors:
            return ActionResult.fail(
                error="VALUE_HELP_VALIDATION_FAILED",
                message="; ".join(validation_errors)
            )

        if request.skip_audit:
            self.executor.enable_audit(False)
        skip_rules = request.skip_validation
        result = self.executor.execute(meta_obj, "crud_create", request.data, skip_rules=skip_rules)

        logger.info(f"[ManageService] create result: success={result.success}, id={result.data.get('id') if result.data else None}")

        if request.skip_audit:
            self.executor.enable_audit(True)

        if result.success and result.last_insert_id:
            try:
                new_data = self.data_source.find_by_id(meta_obj.table_name, result.last_insert_id)
                audit_log_id = self._get_latest_audit_log_id(request.object_type, result.last_insert_id)
                self._publish_change_event(
                    object_type=request.object_type,
                    object_id=result.last_insert_id,
                    event_type="create",
                    new_data=new_data,
                    audit_log_id=audit_log_id
                )
            except Exception as e:
                logger.warning("Failed to publish create event: %s", str(e))

        return result

    def update(self, request: UpdateRequest) -> ActionResult:
        meta_obj = self._get_meta_object(request.object_type)
        params = dict(request.data)
        params["id"] = request.id

        validation_errors = self._validate_value_helps(meta_obj, params)
        if validation_errors:
            return ActionResult.fail(
                error="VALUE_HELP_VALIDATION_FAILED",
                message="; ".join(validation_errors)
            )

        old_data = None
        try:
            old_data = self.data_source.find_by_id(meta_obj.table_name, request.id)
        except Exception:
            pass

        if request.skip_audit:
            self.executor.enable_audit(False)
        skip_rules = request.skip_validation
        result = self.executor.execute(meta_obj, "crud_update", params, skip_rules=skip_rules)
        if request.skip_audit:
            self.executor.enable_audit(True)

        if result.success and old_data:
            try:
                new_data = self.data_source.find_by_id(meta_obj.table_name, request.id)
                audit_log_id = self._get_latest_audit_log_id(request.object_type, request.id)
                self._publish_change_event(
                    object_type=request.object_type,
                    object_id=request.id,
                    event_type="update",
                    old_data=old_data,
                    new_data=new_data,
                    audit_log_id=audit_log_id
                )
            except Exception as e:
                logger.warning("Failed to publish update event: %s", str(e))

        return result

    def delete(self, request: DeleteRequest) -> ActionResult:
        meta_obj = self._get_meta_object(request.object_type)

        logger.info(f"[ManageService.delete] object_type={request.object_type}, id={request.id}, table_name={meta_obj.table_name}")

        old_data = None
        try:
            old_data = self.data_source.find_by_id(meta_obj.table_name, request.id)
            logger.info(f"[ManageService.delete] find_by_id result: {old_data}")
        except Exception as e:
            logger.warning(f"[ManageService.delete] find_by_id exception: {e}")
            pass

        if not old_data:
            logger.info(f"[ManageService.delete] Returning NOT_FOUND")
            return ActionResult.fail(error="NOT_FOUND", message=f"记录不存在: {request.object_type}#{request.id}")

        if meta_obj.deletability and meta_obj.deletability.condition:
            record = old_data
            if not record:
                record = self.data_source.find_by_id(meta_obj.table_name, request.id)
            if record:
                evaluator = ConditionEvaluator()
                context = {"self": record}
                can_delete, msg = evaluator.evaluate_with_message(
                    meta_obj.deletability.condition,
                    meta_obj.deletability.message or "当前条件不允许删除",
                    context=context,
                )
                if not can_delete:
                    return ActionResult.fail(error="DELETABILITY_DENIED", message=msg)

        from meta.core.models import RelationType
        from meta.services.cascade_service import CascadeService

        cascade_service = CascadeService(self.data_source)

        for relation in meta_obj.relations:
            if relation.relation_type == RelationType.COMPOSITION:
                child_meta = registry.get(relation.target_object)
                if child_meta:
                    fk_field = relation.source_field or f"{request.object_type}_id"
                    child_records = self.data_source.find(child_meta.table_name, {fk_field: request.id})
                    if child_records:
                        if not relation.cascade_delete:
                            return ActionResult.fail(
                                error="HAS_COMPOSITION_CHILDREN",
                                message=f"无法删除：存在关联的{child_meta.name or relation.target_object}"
                            )

        before_result = cascade_service.before_delete(request.object_type, request.id)
        if not before_result["can_delete"]:
            return ActionResult.fail(
                error="CASCADE_RESTRICT",
                message="无法删除：存在关联的子对象"
            )

        cascade_result = None
        if before_result["actions"]:
            cascade_result = cascade_service.execute_cascade(before_result["actions"])

        params = {"id": request.id}
        skip_rules = request.force
        result = self.executor.execute(meta_obj, "crud_delete", params, skip_rules=skip_rules)

        if cascade_result and cascade_result.get('_children_audit_info'):
            try:
                self._write_cascade_audit_logs(
                    cascade_result['_parent_object_type'],
                    cascade_result['_parent_object_id'],
                    cascade_result['_children_audit_info']
                )
            except Exception as e:
                logger.warning("Failed to write cascade audit logs: %s", str(e))

        if result.success and old_data:
            try:
                audit_log_id = self._get_latest_audit_log_id(request.object_type, request.id)
                self._publish_change_event(
                    object_type=request.object_type,
                    object_id=request.id,
                    event_type="delete",
                    old_data=old_data,
                    audit_log_id=audit_log_id
                )
            except Exception as e:
                logger.warning("Failed to publish delete event: %s", str(e))

        return result

    def batch_create(self, object_type: str, data_list: List[Dict[str, Any]],
                     skip_validation: bool = False,
                     all_or_none: bool = True) -> BatchOperationResult:
        batch_result = BatchOperationResult()
        meta_obj = self._get_meta_object(object_type)
        
        if all_or_none:
            try:
                with self.data_source.transaction():
                    for data in data_list:
                        result = self.executor.execute(
                            meta_obj, "crud_create", data, skip_rules=skip_validation
                        )
                        batch_result.results.append(result)
                        if result.success:
                            batch_result.success_count += 1
                        else:
                            raise Exception(result.error or result.message or "Create failed")
            except Exception as e:
                batch_result.failed_count = len(data_list) - batch_result.success_count
                batch_result.errors.append(str(e))
        else:
            for data in data_list:
                try:
                    with self.data_source.transaction():
                        result = self.executor.execute(
                            meta_obj, "crud_create", data, skip_rules=skip_validation
                        )
                        batch_result.results.append(result)
                        if result.success:
                            batch_result.success_count += 1
                        else:
                            batch_result.failed_count += 1
                            batch_result.errors.append(result.message or "Create failed")
                except Exception as e:
                    batch_result.failed_count += 1
                    batch_result.errors.append(str(e))
        
        return batch_result

    def batch_update(self, object_type: str, updates: List[Dict[str, Any]],
                     skip_validation: bool = False,
                     all_or_none: bool = True) -> BatchOperationResult:
        batch_result = BatchOperationResult()
        meta_obj = self._get_meta_object(object_type)
        
        if all_or_none:
            try:
                with self.data_source.transaction():
                    for update_data in updates:
                        if "id" not in update_data:
                            raise Exception("Update data missing 'id' field")
                        result = self.executor.execute(
                            meta_obj, "crud_update", update_data, skip_rules=skip_validation
                        )
                        batch_result.results.append(result)
                        if result.success:
                            batch_result.success_count += 1
                        else:
                            raise Exception(result.error or result.message or "Update failed")
            except Exception as e:
                batch_result.failed_count = len(updates) - batch_result.success_count
                batch_result.errors.append(str(e))
        else:
            for update_data in updates:
                if "id" not in update_data:
                    batch_result.failed_count += 1
                    batch_result.errors.append("Update data missing 'id' field")
                    continue
                try:
                    with self.data_source.transaction():
                        result = self.executor.execute(
                            meta_obj, "crud_update", update_data, skip_rules=skip_validation
                        )
                        batch_result.results.append(result)
                        if result.success:
                            batch_result.success_count += 1
                        else:
                            batch_result.failed_count += 1
                            batch_result.errors.append(result.message or "Update failed")
                except Exception as e:
                    batch_result.failed_count += 1
                    batch_result.errors.append(str(e))
        
        return batch_result

    def batch_delete(self, object_type: str, ids: List[Any],
                     force: bool = False,
                     all_or_none: bool = True) -> BatchOperationResult:
        batch_result = BatchOperationResult()
        meta_obj = self._get_meta_object(object_type)
        
        if all_or_none:
            try:
                with self.data_source.transaction():
                    for record_id in ids:
                        params = {"id": record_id}
                        result = self.executor.execute(
                            meta_obj, "crud_delete", params, skip_rules=force
                        )
                        batch_result.results.append(result)
                        if result.success:
                            batch_result.success_count += 1
                        else:
                            raise Exception(result.error or result.message or "Delete failed")
            except Exception as e:
                batch_result.failed_count = len(ids) - batch_result.success_count
                batch_result.errors.append(str(e))
        else:
            for record_id in ids:
                try:
                    with self.data_source.transaction():
                        params = {"id": record_id}
                        result = self.executor.execute(
                            meta_obj, "crud_delete", params, skip_rules=force
                        )
                        batch_result.results.append(result)
                        if result.success:
                            batch_result.success_count += 1
                        else:
                            batch_result.failed_count += 1
                            batch_result.errors.append(result.message or "Delete failed")
                except Exception as e:
                    batch_result.failed_count += 1
                    batch_result.errors.append(str(e))
        
        return batch_result
