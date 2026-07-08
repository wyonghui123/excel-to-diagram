# -*- coding: utf-8 -*-
import logging
from typing import Dict, Any, List, Optional
from meta.core.safe_expr_evaluator import safe_evaluate

from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)


class ConstraintViolation:
    def __init__(self, field_id: str, message: str, constraint_type: str = ''):
        self.field_id = field_id
        self.message = message
        self.constraint_type = constraint_type

    def __repr__(self):
        return f"ConstraintViolation({self.field_id}: {self.message})"


class ConstraintEngine:
    """
    约束引擎 - 基于YAML constraints声明执行校验

    支持的约束类型:
    - unique_scope: 范围内唯一性（如每个产品只能有一个当前版本）
    - immutable: 创建后不可修改（如username）
    - no_delete: 不可删除（如is_system角色）
    """

    def validate(self, context: ActionContext) -> List[ConstraintViolation]:
        violations = []
        meta_obj = context.meta_object
        if meta_obj is None:
            return violations

        for field in meta_obj.fields:
            constraints = getattr(field, 'constraints', None)
            if constraints:
                if isinstance(constraints, list):
                    for constraint in constraints:
                        violation = self._check_constraint(context, field, constraint)
                        if violation:
                            violations.append(violation)
                elif isinstance(constraints, dict):
                    violation = self._check_constraint(context, field, constraints)
                    if violation:
                        violations.append(violation)
            else:
                semantics = getattr(field, 'semantics', None)
                if semantics:
                    immutable = False
                    if isinstance(semantics, dict):
                        immutable = semantics.get('immutable', False)
                    elif hasattr(semantics, 'immutable'):
                        immutable = semantics.immutable

                    if immutable and context.is_update_action:
                        field_id = field.id if isinstance(field.id, str) else str(field.id)
                        new_value = context.params.get(field_id)
                        if new_value is not None and context.old_data:
                            old_value = context.old_data.get(field_id)
                            if old_value is not None and str(old_value) != str(new_value):
                                violations.append(ConstraintViolation(
                                    field_id=field_id,
                                    message=f"{field.name}创建后不可修改",
                                    constraint_type='immutable',
                                ))

        return violations

    def _check_constraint(self, context: ActionContext, field, constraint: Any) -> Optional[ConstraintViolation]:
        if isinstance(constraint, dict):
            constraint_type = constraint.get('type', '')
        elif hasattr(constraint, 'type'):
            constraint_type = getattr(constraint, 'type', '')
            constraint = constraint.__dict__ if hasattr(constraint, '__dict__') else {}
        else:
            return None

        if constraint_type == 'unique_scope':
            return self._check_unique_scope(context, field, constraint)
        elif constraint_type == 'immutable':
            return self._check_immutable(context, field, constraint)
        elif constraint_type == 'no_delete':
            return self._check_no_delete(context, field, constraint)
        elif constraint_type == 'conditional_required':  # [DECORATIVE] [NEW] v1.2 / FR-4.2
            return self._check_conditional_required(context, field, constraint)

        return None

    def _check_unique_scope(self, context: ActionContext, field, constraint: Dict) -> Optional[ConstraintViolation]:
        if not (context.is_create_action or context.is_update_action):
            return None

        condition = constraint.get('condition')
        value = context.params.get(field.id) if isinstance(field.id, str) else None

        if condition:
            try:
                if not safe_evaluate(condition, {'value': value, 'True': True, 'False': False}):
                    return None
            except Exception:
                return None

        if value is None:
            return None

        scope_field = constraint.get('scope')
        if not scope_field:
            return None

        scope_value = context.params.get(scope_field)
        if scope_value is None and context.old_data:
            scope_value = context.old_data.get(scope_field)

        if scope_value is None:
            return None

        table_name = context.meta_object.table_name
        db_col = getattr(field, 'db_column', field.id) if isinstance(field.id, str) else field.id
        sql = f"SELECT id FROM {table_name} WHERE {scope_field} = ? AND {db_col} = ?"
        params = [scope_value, value]

        if context.object_id:
            sql += " AND id != ?"
            params.append(context.object_id)

        try:
            cursor = context.data_source.execute(sql, params)
            existing = cursor.fetchone()
            if existing:
                message = constraint.get('message', f"{field.name}在范围内不唯一")
                return ConstraintViolation(
                    field_id=field.id,
                    message=message,
                    constraint_type='unique_scope',
                )
        except Exception as e:
            logger.warning(f"[ConstraintEngine] unique_scope check error: {e}")

        return None

    def _check_immutable(self, context: ActionContext, field, constraint: Dict) -> Optional[ConstraintViolation]:
        if not context.is_update_action:
            return None

        field_id = field.id if isinstance(field.id, str) else str(field.id)
        new_value = context.params.get(field_id)
        if new_value is None:
            return None

        if context.old_data:
            old_value = context.old_data.get(field_id)
            if old_value is not None and str(old_value) != str(new_value):
                message = constraint.get('message', f"{field.name}不可修改")
                return ConstraintViolation(
                    field_id=field_id,
                    message=message,
                    constraint_type='immutable',
                )

        return None

    def _check_no_delete(self, context: ActionContext, field, constraint: Dict) -> Optional[ConstraintViolation]:
        if not context.is_delete_action:
            return None

        field_id = field.id if isinstance(field.id, str) else str(field.id)

        if context.old_data:
            value = context.old_data.get(field_id)
            if value:
                trigger_value = constraint.get('trigger_value', True)
                if self._values_match(value, trigger_value):
                    message = constraint.get('message', f"该记录不可删除（{field.name}={value}）")
                    return ConstraintViolation(
                        field_id=field_id,
                        message=message,
                        constraint_type='no_delete',
                    )

        return None

    @staticmethod
    def _values_match(actual, expected) -> bool:
        if actual == expected:
            return True
        try:
            if bool(actual) == bool(expected):
                return True
        except (ValueError, TypeError):
            pass
        if str(actual).lower() == str(expected).lower():
            return True
        try:
            if int(actual) == int(expected):
                return True
        except (ValueError, TypeError):
            pass
        return False

    def _check_conditional_required(
        self, context: ActionContext, field, constraint: Dict
    ) -> Optional[ConstraintViolation]:
        """[DECORATIVE] [NEW] v1.2 / FR-4.1: 条件必填校验

        当某个条件的求值结果为 True 时，字段变成必填。

        YAML 示例:
        ```yaml
        fields:
          - id: sub_domain_id
            constraints:
              - type: conditional_required
                condition: "params.get('domain_id') is not None"
                message: "选择领域后，子领域必填"
                severity: error
        ```

        Args:
            context: ActionContext（含 params + old_data + action 类型）
            field: 字段定义
            constraint: 约束声明 dict (含 condition / message / severity)

        Returns:
            ConstraintViolation or None
        """
        # 仅在 create/update 时校验（read/list/delete 不需要）
        if not (context.is_create_action or context.is_update_action):
            return None

        field_id = field.id if isinstance(field.id, str) else str(field.id)
        new_value = context.params.get(field_id)

        # 已有值 → 跳过（满足必填要求）
        if new_value is not None and new_value != '':
            return None

        # 评估条件
        condition = constraint.get('condition', '')
        if not condition:
            return None

        # 构造求值上下文
        eval_data = {
            'value': new_value,
            'old_value': context.old_data.get(field_id) if context.old_data else None,
            'params': dict(context.params) if context.params else {},
            'old_data': dict(context.old_data) if context.old_data else {},
            'True': True,
            'False': False,
            'None': None,
        }

        try:
            condition_met = safe_evaluate(condition, eval_data)
        except Exception as e:
            logger.warning(f"[ConstraintEngine] conditional_required condition eval error: {e}")
            return None

        if not condition_met:
            return None

        # 条件满足但字段为空 → 违反约束
        return ConstraintViolation(
            field_id=field_id,
            message=constraint.get('message', f'{getattr(field, "name", field_id)}为条件必填字段'),
            constraint_type='conditional_required',
        )
