# -*- coding: utf-8 -*-
import logging
import os
from typing import Any, Dict, List, Optional

from meta.core.action_context import ActionContext, ActionResult
from meta.core.interceptors.base import Interceptor
from meta.core.models import registry
from meta.core.datasource import get_data_source
from meta.core.action_constants import CRUD_CREATE, CRUD_UPDATE, CRUD_DELETE
from meta.core.table_name_validator import validate_table_name
from meta.core.association_engine import AssociationEngine
from meta.core.deep_insert_engine import DeepInsertEngine
from meta.services.display_name_service import DisplayNameService
from meta.core.ui_config.config_builder import UIConfigBuilder
from meta.core.ui_config.value_help_formatter import value_help_to_dict as _value_help_to_dict_impl

logger = logging.getLogger(__name__)

BO_INTERCEPTOR_MODE = os.environ.get('BO_INTERCEPTOR_MODE', 'sync')


class BOFramework:
    """
    统一业务对象框架

    提供统一的元数据驱动 BO 操作入口，自动触发拦截器链。

    增强:
    - 集成 AssociationEngine (元数据驱动关联)
    - 集成 ConstraintEngine (声明式约束校验)
    - 支持 associate/dissociate/query_associations
    - 支持 get_ui_config
    """

    def __init__(self, data_source=None):
        import os as _os
        # [DECORATIVE] v3.18 P0: 优先尊重 SQLITE_DB_PATH / ARCH_DB_PATH 环境变量
        # (test.py 创建的 snapshot DB 通过该环境变量指定, 之前被忽略)
        env_db_path = (
            _os.environ.get('SQLITE_DB_PATH')
            or _os.environ.get('ARCH_DB_PATH')
        )
        if env_db_path:
            default_db_path = env_db_path
        else:
            default_db_path = _os.path.join(
                _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                'architecture.db'
            )
        self._data_source = data_source or get_data_source('sqlite', database=default_db_path)
        self._interceptors: List[Interceptor] = []
        self._user_context: Dict[str, Any] = {}
        self._association_engine = AssociationEngine()
        self._deep_insert_engine = DeepInsertEngine()
        self._action_handlers: Dict[str, Dict[str, Any]] = {}
        self._display_name_service = DisplayNameService(registry)
        self._ui_config_builder = UIConfigBuilder(
            self._display_name_service, BOFramework._infer_navigation)
        self._async_engine = None
        self._async_audit_writer = None

    @property
    def interceptors(self) -> List[Interceptor]:
        return self._interceptors

    def register_interceptor(self, interceptor: Interceptor) -> 'BOFramework':
        self._interceptors.append(interceptor)
        self._interceptors.sort(key=lambda x: x.priority)
        logger.info(f"[BOFramework] Registered interceptor: {interceptor.name} (priority={interceptor.priority})")
        return self

    def _ensure_async_engine(self):
        if self._async_engine is not None:
            return
        if BO_INTERCEPTOR_MODE != 'async':
            return
        from meta.core.async_interceptor_engine import AsyncInterceptorEngine
        from meta.services.async_audit_writer import AsyncAuditWriter
        self._async_audit_writer = AsyncAuditWriter()
        self._async_audit_writer.set_data_source(self._data_source)
        self._async_engine = AsyncInterceptorEngine(
            self._interceptors,
            async_audit_writer=self._async_audit_writer
        )
        logger.info("[BOFramework] Async interceptor engine initialized")

    def set_user_context(self, user_id: int = None, user_name: str = None,
                         ip_address: str = None, trace_id: str = None):
        self._user_context = {
            'user_id': user_id,
            'user_name': user_name,
            'ip_address': ip_address,
            'trace_id': trace_id,
        }

    def set_audit_user(self, user_id: int = None, user_name: str = None,
                       ip_address: str = None, trace_id: str = None):
        self.set_user_context(user_id, user_name, ip_address, trace_id)

    def execute(self, object_type: str, action: str, params: Dict[str, Any]) -> ActionResult:
        logger.debug("[BOFramework] execute START: object_type=%s, action=%s", object_type, action)
        
        meta_object = registry.get(object_type)
        if not meta_object:
            return ActionResult(success=False, message=f"Unknown object type: {object_type}")

        context = ActionContext(
            meta_object=meta_object,
            action=action,
            params=params,
            data_source=self._data_source,
            **self._user_context,
        )

        try:
            if action in (CRUD_UPDATE, CRUD_DELETE):
                self._load_old_data(context)

            # [Constraint 双轨消除 2026-06-07]
            # 约束校验统一由 ConstraintValidationInterceptor(P42) 在拦截器链中执行，
            # 不再在 bo_framework.execute() 中重复调用 _constraint_engine。
            # 拦截器提供更丰富的错误格式（ValidationFailedError + i18n_key + ValidationDetail）。

            # [M5.2 2026-06-05] 拦截器链事务基线
            # 默认行为：CRUD/associate 动作自动包裹事务
            # 环境变量 DISABLE_AUTO_TRANSACTION=true 可关闭
            _DISABLE = os.environ.get('DISABLE_AUTO_TRANSACTION', '').lower() in ('1', 'true', 'yes')
            _AUTO_TXN_ACTIONS = (
                CRUD_CREATE, CRUD_UPDATE, CRUD_DELETE,
                'associate', 'dissociate',
                'assign', 'unassign',
                'batch_assign', 'batch_unassign',
            )
            _should_wrap = (
                not _DISABLE
                and action in _AUTO_TXN_ACTIONS
                and hasattr(self._data_source, 'in_transaction')
                and not self._data_source.in_transaction
            )

            if _should_wrap:
                # 复用现有 bo_framework.transaction() context（生成 transaction_id）
                with self.transaction() as txn_ctx:
                    context.transaction_id = txn_ctx.transaction_id
                    self._dispatch_interceptors(context)
                    # 检查 result 标记事务失败
                    if context.result and not context.result.success:
                        raise _TxnMarker(
                            f"action reported failure: {context.result.message}",
                            result=context.result,
                        )
                # [审计延迟写入 2026-06-09]
                # 事务提交后，flush 缓存的审计记录
                self._flush_pending_audit_records(context)
                return context.result or ActionResult(success=True, message="Operation completed")
            else:
                self._dispatch_interceptors(context)
                logger.debug("[BOFramework] execute END: result=%s", context.result)
                return context.result or ActionResult(success=True, message="Operation completed")

        except Exception as e:
            from meta.core.exceptions import FieldPolicyViolationError, ValidationFailedError
            if isinstance(e, FieldPolicyViolationError):
                logger.info(f"[BOFramework] FieldPolicy validation FAILED: {e}")
                return ActionResult(success=False, message=str(e))
            if isinstance(e, ValidationFailedError):
                logger.info(f"[BOFramework] Validation FAILED: {e}")
                return ActionResult(success=False, message=str(e), errors=e.details)
            from meta.core.interceptors.permission_interceptor import PermissionDenied
            if isinstance(e, PermissionDenied):
                logger.info(f"[BOFramework] PermissionDenied: {e.detail}")
                return ActionResult(success=False, message=e.detail, status_code=403)
            logger.error(f"[BOFramework] Error executing {action} on {object_type}: {e}")
            self._execute_error_interceptors(context, e)
            return ActionResult(success=False, message=str(e), errors=[str(e)])

    def _execute_interceptors_async(self, context: ActionContext):
        self._async_engine.execute_before(context)
        self._execute_core(context)
        self._async_engine.execute_after(context)

    def _dispatch_interceptors(self, context: ActionContext) -> None:
        """[M5.2 2026-06-05] 统一执行拦截器链（事务上下文内的 helper）。

        原逻辑从 execute() 抽出，供事务包裹路径和原路径共用。
        """
        self._ensure_async_engine()
        if self._async_engine is not None:
            self._execute_interceptors_async(context)
        else:
            self._execute_before_interceptors(context)
            self._execute_core(context)
            self._execute_after_interceptors(context)

    def _load_old_data(self, context: ActionContext):
        if context.old_data is not None:
            return
        table_name = validate_table_name(context.meta_object.table_name)
        object_id = context.object_id
        if not object_id:
            return
        try:
            cursor = context.data_source.execute(
                f"SELECT * FROM {table_name} WHERE id = ?",
                [object_id]
            )
            row = cursor.fetchone()
            if row:
                if isinstance(row, dict):
                    context.old_data = row
                else:
                    cols = [desc[0] for desc in cursor.description]
                    context.old_data = dict(zip(cols, row))
        except Exception as e:
            logger.debug(f"[BOFramework] Failed to load old data: {e}")

    def _execute_before_interceptors(self, context: ActionContext):
        for interceptor in self._interceptors:
            if interceptor.should_execute(context):
                interceptor.before_action(context)

    def _execute_core(self, context: ActionContext):
        logger.debug(f"[BOFramework] _execute_core: action={context.action}, delegating to PersistenceInterceptor")

    def _execute_after_interceptors(self, context: ActionContext):
        for interceptor in reversed(self._interceptors):
            if interceptor.should_execute(context):
                interceptor.after_action(context)

    def _execute_error_interceptors(self, context: ActionContext, error: Exception):
        for interceptor in reversed(self._interceptors):
            try:
                interceptor.on_error(context, error)
            except Exception as e:
                logger.error(f"[BOFramework] Error in {interceptor.name}.on_error: {e}")

    def create(self, object_type: str, data: Dict[str, Any]) -> ActionResult:
        return self.execute(object_type, CRUD_CREATE, data)

    def read(self, object_type: str, id: int) -> ActionResult:
        return self.execute(object_type, 'crud_read', {'id': id})

    def update(self, object_type: str, id: int, data: Dict[str, Any]) -> ActionResult:
        params = {'id': id, **data}
        return self.execute(object_type, CRUD_UPDATE, params)

    def delete(self, object_type: str, id: int) -> ActionResult:
        return self.execute(object_type, CRUD_DELETE, {'id': id})

    def query(self, object_type: str, filters: Dict[str, Any] = None,
              page: int = 1, page_size: int = 20) -> ActionResult:
        params = {
            'filters': filters or {},
            'page': page,
            'page_size': page_size,
        }
        return self.execute(object_type, 'crud_query', params)

    def deep_insert(self, object_type: str, params: Dict[str, Any]) -> ActionResult:
        return self._deep_insert_engine.execute(object_type, params, self._data_source)

    def register_action_handler(self, object_type: str, action_id: str, handler) -> 'BOFramework':
        if object_type not in self._action_handlers:
            self._action_handlers[object_type] = {}
        self._action_handlers[object_type][action_id] = handler
        logger.info(f"[BOFramework] Registered action handler: {object_type}.{action_id}")
        return self

    def get_action_handler(self, object_type: str, action_id: str):
        handlers = self._action_handlers.get(object_type, {})
        return handlers.get(action_id)

    def execute_action(self, object_type: str, action: str, params: Dict[str, Any]) -> ActionResult:
        return self.execute(object_type, action, params)

    def associate(self, src_type: str, src_id: int, tgt_type: str, tgt_id: int,
                  association_name: str = None, metadata: dict = None) -> ActionResult:
        logger.info(f"[BOFramework] associate: {src_type}:{src_id} -> {tgt_type}:{tgt_id} ({association_name})")
        params = {
            'src_id': src_id,
            'tgt_type': tgt_type,
            'tgt_id': tgt_id,
            'association_name': association_name,
            'metadata': metadata or {},
        }
        result = self.execute(src_type, 'associate', params)
        logger.info(f"[BOFramework] associate result: success={result.success}")
        return result

    def dissociate(self, src_type: str, src_id: int, tgt_type: str, tgt_id: int,
                   association_name: str = None) -> ActionResult:
        logger.info(f"[BOFramework] dissociate: {src_type}:{src_id} -/-> {tgt_type}:{tgt_id} ({association_name})")
        params = {
            'src_id': src_id,
            'tgt_type': tgt_type,
            'tgt_id': tgt_id,
            'association_name': association_name,
        }
        result = self.execute(src_type, 'dissociate', params)
        logger.info(f"[BOFramework] dissociate result: success={result.success}")
        return result

    def query_associations(self, src_type: str, src_id: int, association_name: str,
                           page: int = 1, page_size: int = 50, search: str = None,
                           filters: Optional[Dict[str, Any]] = None,
                           ordering: str = None) -> ActionResult:
        params = {
            'src_id': src_id,
            'association_name': association_name,
            'page': page,
            'page_size': page_size,
            'search': search,
        }
        if filters:
            params['filters'] = dict(filters)
        if ordering:
            params['ordering'] = ordering
        return self.execute(src_type, 'query_associations', params)

    def assign_association(self, src_type: str, src_id: int, tgt_type: str, tgt_id: int,
                          association_name: str = None, metadata: dict = None) -> ActionResult:
        logger.info(f"[BOFramework] assign_association: {src_type}:{src_id} -> {tgt_type}:{tgt_id} ({association_name})")
        params = {
            'src_id': src_id,
            'tgt_type': tgt_type,
            'tgt_id': tgt_id,
            'association_name': association_name,
            'metadata': metadata or {},
        }
        result = self.execute(src_type, 'assign', params)
        logger.info(f"[BOFramework] assign_association result: success={result.success}")
        return result

    def unassign_association(self, src_type: str, src_id: int, tgt_type: str, tgt_id: int,
                            association_name: str = None) -> ActionResult:
        logger.info(f"[BOFramework] unassign_association: {src_type}:{src_id} -/-> {tgt_type}:{tgt_id} ({association_name})")
        params = {
            'src_id': src_id,
            'tgt_type': tgt_type,
            'tgt_id': tgt_id,
            'association_name': association_name,
        }
        result = self.execute(src_type, 'unassign', params)
        logger.info(f"[BOFramework] unassign_association result: success={result.success}")
        return result

    def batch_assign_associations(self, src_type: str, src_id: int, tgt_type: str,
                                  target_ids: List[int], association_name: str = None,
                                  metadata: dict = None) -> ActionResult:
        logger.info(f"[BOFramework] batch_assign_associations: {src_type}:{src_id} -> {target_ids} ({association_name})")
        params = {
            'src_id': src_id,
            'tgt_type': tgt_type,
            'target_ids': target_ids,
            'association_name': association_name,
            'metadata': metadata or {},
        }
        result = self.execute(src_type, 'batch_assign', params)
        logger.info(f"[BOFramework] batch_assign_associations result: success={result.success}")
        return result

    def batch_unassign_associations(self, src_type: str, src_id: int, tgt_type: str,
                                     target_ids: List[int], association_name: str = None) -> ActionResult:
        logger.info(f"[BOFramework] batch_unassign_associations: {src_type}:{src_id} -/-> {target_ids} ({association_name})")
        params = {
            'src_id': src_id,
            'tgt_type': tgt_type,
            'target_ids': target_ids,
            'association_name': association_name,
        }
        result = self.execute(src_type, 'batch_unassign', params)
        logger.info(f"[BOFramework] batch_unassign_associations result: success={result.success}")
        return result

    def count_associations(self, src_type: str, src_id: int, association_name: str) -> ActionResult:
        logger.info(f"[BOFramework] count_associations: {src_type}:{src_id} ({association_name})")
        params = {
            'src_id': src_id,
            'association_name': association_name,
        }
        result = self.execute(src_type, 'count', params)
        logger.info(f"[BOFramework] count_associations result: success={result.success}, data={result.data}")
        return result

    def batch_query_associations(self, src_type: str, source_ids: List[int],
                                  association_name: str, page: int = 1,
                                  page_size: int = 20, search: str = None) -> ActionResult:
        params = {
            'source_ids': source_ids,
            'association_name': association_name,
            'page': page,
            'page_size': page_size,
            'search': search,
        }
        return self.execute(src_type, 'batch_query_associations', params)

    def retrieve_with_associations(self, object_type: str, obj_id: int,
                                  associations: List[str] = None,
                                  depth: int = 1) -> ActionResult:
        logger.info(f"[BOFramework] retrieve_with_associations: {object_type}:{obj_id}, associations={associations}, depth={depth}")

        if depth > 2:
            return ActionResult(success=False, message="深度限制为2，防止循环引用")

        result = self.read(object_type, obj_id)
        if not result.success:
            return result

        data = result.data.copy() if result.data else {}

        if associations and depth > 0:
            meta_obj = registry.get(object_type)
            if meta_obj:
                obj_associations = getattr(meta_obj, 'associations', {}) or {}
                for assoc_name in associations:
                    assoc_def = obj_associations.get(assoc_name) if isinstance(obj_associations, dict) else None
                    if assoc_def:
                        assoc_result = self.query_associations(
                            src_type=object_type,
                            src_id=obj_id,
                            association_name=assoc_name,
                            page=1,
                            page_size=100
                        )
                        if assoc_result.success:
                            data[f'_assoc_{assoc_name}'] = assoc_result.data

        return ActionResult(success=True, data=data, message="深度获取成功")

    def get_ui_config(self, object_type: str, view_name: str = None) -> dict:
        return self._ui_config_builder.build(object_type, view_name)

    def get_schema(self, object_type: str) -> dict:
        meta_obj = registry.get(object_type)
        if not meta_obj:
            return {}

        schema = {
            'object_type': meta_obj.id,
            'name': meta_obj.name,
            'table_name': getattr(meta_obj, 'table_name', ''),
            'description': getattr(meta_obj, 'description', ''),
        }

        fields_schema = []
        for f in meta_obj.fields:
            fs = {
                'id': f.id,
                'name': f.name,
                'type': str(f.field_type) if hasattr(f, 'field_type') else 'string',
                'required': getattr(f, 'required', False),
                'unique': getattr(f, 'unique', False),
                'description': getattr(f, 'description', ''),
            }
            default = getattr(f, 'default', None)
            if default is not None:
                fs['default'] = default
            constraints = getattr(f, 'constraints', None)
            if constraints:
                fs['constraints'] = self._make_json_safe(constraints)
            value_help = getattr(f, 'value_help', None)
            if value_help:
                fs['value_help'] = self._make_json_safe(self._value_help_to_dict(value_help))
            enum_values = getattr(f, 'enum_values', None)
            if enum_values:
                fs['enum_values'] = self._make_json_safe(enum_values)
            enum_type = getattr(f, 'enum_type', None)
            if enum_type:
                fs['enum_type'] = enum_type
            ui = getattr(f, 'ui', None)
            if ui:
                fs['ui'] = self._make_json_safe(self._ui_to_dict(ui))
            fields_schema.append(fs)
        schema['fields'] = fields_schema

        associations = getattr(meta_obj, 'associations', None)
        if associations:
            assoc_list = []
            if isinstance(associations, dict):
                for name, assoc in associations.items():
                    a = self._make_json_safe(assoc)
                    a['name'] = name
                    assoc_list.append(a)
            elif isinstance(associations, list):
                for assoc in associations:
                    a = self._make_json_safe(assoc)
                    assoc_list.append(a)
            schema['associations'] = assoc_list

        hierarchy = getattr(meta_obj, 'hierarchy', None)
        if hierarchy:
            schema['hierarchy'] = hierarchy

        authorization = getattr(meta_obj, 'authorization', None)
        if authorization:
            schema['authorization'] = self._make_json_safe(authorization)

        return schema

    def begin_transaction(self, isolation_level: str = 'READ_COMMITTED') -> str:
        import uuid
        transaction_id = str(uuid.uuid4())[:8]
        if hasattr(self._data_source, 'begin_transaction'):
            self._data_source.begin_transaction()
        logger.info(f"[BOFramework] Transaction started: {transaction_id}")
        return transaction_id

    def commit(self, transaction_id: str = None) -> bool:
        try:
            if hasattr(self._data_source, 'commit'):
                self._data_source.commit()
            logger.info(f"[BOFramework] Transaction committed: {transaction_id}")
            return True
        except Exception as e:
            logger.error(f"[BOFramework] Commit failed: {e}")
            return False

    def rollback(self, transaction_id: str = None) -> bool:
        try:
            if hasattr(self._data_source, 'rollback'):
                self._data_source.rollback()
            logger.info(f"[BOFramework] Transaction rolled back: {transaction_id}")
            return True
        except Exception as e:
            logger.error(f"[BOFramework] Rollback failed: {e}")
            return False

    def transaction(self):
        return TransactionContext(self)

    def _flush_pending_audit_records(self, context) -> None:
        """[审计延迟写入 2026-06-09]
        事务提交后，flush 缓存的审计记录到数据库。
        
        Args:
            context: ActionContext，包含 _pending_audit_records 列表
        """
        pending = getattr(context, '_pending_audit_records', [])
        if not pending:
            return
        
        # 导入 StructuredLogger（延迟导入避免循环依赖）
        # 不传入 async_writer，直接同步写入
        from meta.services.structured_logger import StructuredLogger
        structured_logger = StructuredLogger(async_writer=None)
        
        flushed = 0
        for audit_params in pending:
            try:
                structured_logger.log_business(**audit_params)
                flushed += 1
            except Exception as e:
                logger.error(
                    f"[BOFramework] Failed to flush audit record: {e}, "
                    f"action={audit_params.get('action')}, "
                    f"object_type={audit_params.get('object_type')}, "
                    f"object_id={audit_params.get('object_id')}"
                )
        
        if flushed > 0:
            logger.info(
                f"[BOFramework] Flushed {flushed}/{len(pending)} pending audit records "
                f"after transaction commit"
            )
        
        # 清空缓存
        context._pending_audit_records.clear()

    @staticmethod
    def _infer_navigation(assoc: dict):
        if assoc.get('navigation') is not None:
            return

        from meta.core.metadata_resolver import MetadataResolver

        assoc_type = assoc.get('type', 'many_to_many')
        enabled = MetadataResolver.is_navigation_enabled(assoc_type)

        target_entity = assoc.get('target_entity') or assoc.get('target_type') or ''
        icon = MetadataResolver.get_entity_icon(target_entity)

        label = (assoc.get('navigation', {}) or {}).get('label')
        if not label:
            label = assoc.get('label')
        if not label:
            label = assoc.get('name', '')

        readonly = assoc.get('readonly', False)

        assoc['navigation'] = {
            'enabled': enabled,
            'label': label,
            'icon': icon,
            'display_mode': 'list',
            'readonly': readonly,
        }

    @staticmethod
    def _make_json_safe(obj):
        if isinstance(obj, dict):
            return {k: BOFramework._make_json_safe(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [BOFramework._make_json_safe(item) for item in obj]
        elif isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        elif hasattr(obj, '__dict__'):
            return BOFramework._make_json_safe(obj.__dict__)
        else:
            return str(obj)

    def _value_help_to_dict(self, vh):
        return _value_help_to_dict_impl(vh)

    def _ui_to_dict(self, ui):
        if not ui:
            return {}
        d = {}
        for key in ['widget', 'visible', 'editable', 'readonly', 'hidden',
                    'hidden_in_detail', 'hidden_in_form', 'hidden_in_list',
                    'readonly_in_create', 'placeholder', 'order', 'width',
                    'relation', 'display_field', 'depends_on', 'cascade_group',
                    'cascade_level', 'lineItem', 'fieldGroup', 'importance']:
            val = getattr(ui, key, None)
            if val is not None and val != '' and val != False:
                d[key] = val
        return d


class TransactionContext:
    def __init__(self, bo_framework: BOFramework):
        self.bo_framework = bo_framework
        self.transaction_id = None

    def __enter__(self):
        self.transaction_id = self.bo_framework.begin_transaction()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.bo_framework.commit(self.transaction_id)
        else:
            self.bo_framework.rollback(self.transaction_id)
            logger.error(f"[TransactionContext] Transaction rolled back due to error: {exc_val}")
        return False


class _TxnMarker(Exception):
    """[M5.2 2026-06-05] 事务回滚标记。

    当 action 报告 failure 但未抛异常时，BOFramework 抛此异常
    以触发 with 块退出时的 rollback。
    """
    def __init__(self, message: str, result: Optional[ActionResult] = None):
        super().__init__(message)
        self.result = result


bo_framework = BOFramework()
