# -*- coding: utf-8 -*-
"""
[MODULE] permission_config_loader �?Phase 7 声明式配置加载器
[DESCRIPTION] �?BO.yaml permission: 块加载权限规�? upsert �?data_permission_rules �?[SPEC] spec-permission-system-unification-2026-07-19 §3.11 / §4.5 / §8.7

[设计原则]
  - parse_file(yaml_path) �?Dict[rule_name, rule_dict]  (纯解�? 不写�?
  - load_from_yaml(yaml_path, permission_set_id) �?int (新插入数, upsert 幂等)
  - validate_rule(rule_dict) �?None / raise PermissionConfigValidationError
  - Secure-by-Default: 非法配置立即报错, 不静默跳�?
[permission 块示例]
  permission:
    default:
      rule_type: dimension        # 必须: dimension/condition/owner/prohibition/visibility
      dimension_code: product     # dimension 类型必须
      scope_mode: include         # 可�? include/exclude (默认 include)
      permission_level: read      # 可�? read/write/delete/* (默认 read)
      inherit_to_children: true   # 可�? true/false (默认 true)
      propagate_to_parents: false # 可�? true/false (默认 false)
    prohibit_archived:
      rule_type: prohibition
      resource_type: sample
      condition: "status = 'archived'"
      is_denied: true             # prohibition 类型必须�?true
"""
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)


# ============================================================================
# [P7-T1] 常量: 允许�?rule_type / scope_mode / permission_level
# ============================================================================

PERMITTED_RULE_TYPES = {
    'dimension',
    'condition',
    'owner',
    'prohibition',
    'visibility',
}

PERMITTED_SCOPE_MODES = {
    'include',
    'exclude',
}

PERMITTED_PERMISSION_LEVELS = {
    'read',
    'write',
    'delete',
    'manage',
    '*',
}

# 默认�?_DEFAULT_SCOPE_MODE = 'include'
_DEFAULT_PERMISSION_LEVEL = 'read'
_DEFAULT_INHERIT_TO_CHILDREN = 1
_DEFAULT_PROPAGATE_TO_PARENTS = 0
_DEFAULT_IS_DENIED = 0


# ============================================================================
# [P7-T4] 自定义异�?# ============================================================================

class PermissionConfigValidationError(Exception):
    """[P7-T4] 配置校验失败异常

    用于启动时检测到非法 permission: 块配�? 立即报错阻止启动�?    """


# ============================================================================
# [P7-T1/T4] PermissionConfigLoader
# ============================================================================

class PermissionConfigLoader:
    """[P7-T1/T2/T4] 声明式配置加载器

    Phase 7 范围:
      P7-T1: parse_file() 解析 permission: �?      P7-T2: load_from_yaml() upsert �?data_permission_rules
      P7-T4: validate_rule() 校验 rule_type/dimension/condition

    用法:
        loader = PermissionConfigLoader(data_source=ds)
        n = loader.load_from_yaml('schemas/product.yaml', permission_set_id=1)
        # n = 新插入数 (0 表示幂等无新�?
    """

    def __init__(self, data_source=None):
        """构�?PermissionConfigLoader

        Args:
            data_source: DB 数据�?(None 仅用�?parse_file 离线校验)
        """
        self._ds = data_source

    # ------------------------------------------------------------------------
    # P7-T1: parse_file �?解析 YAML �?permission: �?    # ------------------------------------------------------------------------

    def parse_file(self, yaml_path: str) -> Dict[str, Dict[str, Any]]:
        """[P7-T1] 解析 BO.yaml 文件, 提取 permission: �?
        Args:
            yaml_path: BO.yaml 文件路径

        Returns:
            Dict[rule_name, rule_dict] �?规则�?�?规则字典

        Raises:
            PermissionConfigValidationError: 配置非法�?            FileNotFoundError: 文件不存�?        """
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f'BO.yaml not found: {yaml_path}')

        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}

        permission_block = data.get('permission') or {}
        if not permission_block:
            return {}

        if not isinstance(permission_block, dict):
            raise PermissionConfigValidationError(
                f'permission block must be a dict, got {type(permission_block).__name__} '
                f'in {yaml_path}'
            )

        # 校验每条规则
        parsed: Dict[str, Dict[str, Any]] = {}
        bo_id = data.get('id') or ''
        for rule_name, rule_def in permission_block.items():
            if not isinstance(rule_def, dict):
                raise PermissionConfigValidationError(
                    f'permission rule "{rule_name}" must be a dict, got '
                    f'{type(rule_def).__name__} in {yaml_path}'
                )
            # 添加元信�?            normalized = self._normalize_rule(rule_def, rule_name, bo_id, yaml_path)
            # 校验
            self.validate_rule(normalized, rule_name, yaml_path)
            parsed[rule_name] = normalized

        return parsed

    # ------------------------------------------------------------------------
    # P7-T2: load_from_yaml �?upsert �?data_permission_rules
    # ------------------------------------------------------------------------

    def load_from_yaml(self, yaml_path: str, permission_set_id: int) -> int:
        """[P7-T2] 加载 YAML �?upsert �?data_permission_rules �?
        upsert 幂等策略:
          - 唯一�? (permission_set_id, rule_type, resource_type, dimension_code, condition, permission_level)
          - 已存在则跳过 (不更�? 避免覆盖用户后续修改)
          - 不存在则插入

        Args:
            yaml_path: BO.yaml 文件路径
            permission_set_id: 关联角色 ID

        Returns:
            int �?新插入的规则�?(0 = 全部已存�? 幂等)

        Raises:
            PermissionConfigValidationError: 配置非法
            ValueError: data_source �?None
        """
        if self._ds is None:
            raise ValueError('data_source is required for load_from_yaml()')

        rules = self.parse_file(yaml_path)
        if not rules:
            return 0

        inserted = 0
        now = datetime.now().isoformat()
        for rule_name, rule_def in rules.items():
            # 检查是否已存在 (幂等)
            if self._rule_exists(rule_def, permission_set_id):
                logger.debug(
                    f'[P7-T2] skip existing rule: permission_set_id={permission_set_id} '
                    f'rule_type={rule_def.get("rule_type")} '
                    f'dimension_code={rule_def.get("dimension_code")} '
                    f'condition={rule_def.get("condition")}'
                )
                continue

            # 插入
            self._insert_rule(rule_def, permission_set_id, now)
            inserted += 1
            logger.info(
                f'[P7-T2] inserted rule: permission_set_id={permission_set_id} '
                f'rule_type={rule_def.get("rule_type")} '
                f'name={rule_name}'
            )

        return inserted

    # ------------------------------------------------------------------------
    # P7-T4: validate_rule �?配置校验
    # ------------------------------------------------------------------------

    def validate_rule(
        self,
        rule: Dict[str, Any],
        rule_name: str = '',
        yaml_path: str = '',
    ) -> None:
        """[P7-T4] 校验单条规则

        校验�?
          1. rule_type 必须�?PERMITTED_RULE_TYPES �?          2. dimension 类型必须�?dimension_code
          3. condition 类型必须�?condition 字段
          4. prohibition 类型 is_denied 必须�?True/1
          5. scope_mode 必须�?PERMITTED_SCOPE_MODES �?(如有)
          6. permission_level 必须�?PERMITTED_PERMISSION_LEVELS �?(如有)

        Args:
            rule: 规则字典
            rule_name: 规则�?(错误消息�?
            yaml_path: 文件路径 (错误消息�?

        Raises:
            PermissionConfigValidationError: 任何校验失败
        """
        ctx = f'rule="{rule_name}" file={yaml_path}' if rule_name else f'file={yaml_path}'

        # 1. rule_type 必须
        rt = rule.get('rule_type')
        if not rt:
            raise PermissionConfigValidationError(
                f'permission rule missing "rule_type" ({ctx})'
            )
        if rt not in PERMITTED_RULE_TYPES:
            raise PermissionConfigValidationError(
                f'invalid rule_type "{rt}" ({ctx}); '
                f'permitted: {sorted(PERMITTED_RULE_TYPES)}'
            )

        # 2. dimension 类型必须�?dimension_code
        if rt == 'dimension':
            if not rule.get('dimension_code'):
                raise PermissionConfigValidationError(
                    f'dimension rule must have "dimension_code" ({ctx})'
                )

        # 3. condition 类型必须�?condition
        if rt == 'condition':
            if not rule.get('condition'):
                raise PermissionConfigValidationError(
                    f'condition rule must have "condition" ({ctx})'
                )

        # 4. prohibition 类型 is_denied 必须�?True/1
        if rt == 'prohibition':
            is_denied = rule.get('is_denied', _DEFAULT_IS_DENIED)
            if not _is_truthy(is_denied):
                raise PermissionConfigValidationError(
                    f'prohibition rule must have is_denied=true/1 ({ctx}); '
                    f'got is_denied={is_denied!r}'
                )

        # 5. scope_mode 校验 (如有)
        sm = rule.get('scope_mode')
        if sm is not None and sm not in PERMITTED_SCOPE_MODES:
            raise PermissionConfigValidationError(
                f'invalid scope_mode "{sm}" ({ctx}); '
                f'permitted: {sorted(PERMITTED_SCOPE_MODES)}'
            )

        # 6. permission_level 校验 (如有)
        pl = rule.get('permission_level')
        if pl is not None and pl not in PERMITTED_PERMISSION_LEVELS:
            raise PermissionConfigValidationError(
                f'invalid permission_level "{pl}" ({ctx}); '
                f'permitted: {sorted(PERMITTED_PERMISSION_LEVELS)}'
            )

    # ========================================================================
    # 内部辅助方法
    # ========================================================================

    def _normalize_rule(
        self,
        rule_def: Dict[str, Any],
        rule_name: str,
        bo_id: str,
        yaml_path: str,
    ) -> Dict[str, Any]:
        """[P7-T1] 规范化规�? 填充默认�?+ 元信�?""
        normalized = dict(rule_def)

        # 填充默认�?        normalized.setdefault('scope_mode', _DEFAULT_SCOPE_MODE)
        normalized.setdefault('permission_level', _DEFAULT_PERMISSION_LEVEL)
        normalized.setdefault('inherit_to_children', _DEFAULT_INHERIT_TO_CHILDREN)
        normalized.setdefault('propagate_to_parents', _DEFAULT_PROPAGATE_TO_PARENTS)
        normalized.setdefault('is_denied', _DEFAULT_IS_DENIED)

        # 元信�?        normalized['_rule_name'] = rule_name
        normalized['_bo_id'] = bo_id
        normalized['_source'] = os.path.basename(yaml_path)

        # bool �?int 转换 (DB �?int)
        for k in ('inherit_to_children', 'propagate_to_parents', 'is_denied'):
            if isinstance(normalized.get(k), bool):
                normalized[k] = 1 if normalized[k] else 0

        return normalized

    def _rule_exists(self, rule: Dict[str, Any], permission_set_id: int) -> bool:
        """[P7-T2] 检查规则是否已存在 (幂等判定)"""
        sql = (
            "SELECT COUNT(*) FROM data_permission_rules "
            "WHERE permission_set_id = ? AND rule_type = ? "
            "AND COALESCE(resource_type, '') = COALESCE(?, '') "
            "AND COALESCE(dimension_code, '') = COALESCE(?, '') "
            "AND COALESCE(condition, '') = COALESCE(?, '') "
            "AND COALESCE(permission_level, '') = COALESCE(?, '')"
        )
        params = (
            permission_set_id,
            rule.get('rule_type'),
            rule.get('resource_type'),
            rule.get('dimension_code'),
            rule.get('condition'),
            rule.get('permission_level'),
        )
        cursor = self._ds.execute(sql, params)
        row = cursor.fetchone()
        return bool(row and row[0] > 0)

    def _insert_rule(self, rule: Dict[str, Any], permission_set_id: int, now: str) -> None:
        """[P7-T2] 插入规则�?data_permission_rules"""
        sql = (
            "INSERT INTO data_permission_rules "
            "(permission_set_id, rule_type, resource_type, dimension_code, condition, "
            "scope_mode, permission_level, is_denied, inherit_to_children, "
            "propagate_to_parents, source_table, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        params = (
            permission_set_id,
            rule.get('rule_type'),
            rule.get('resource_type'),
            rule.get('dimension_code'),
            rule.get('condition'),
            rule.get('scope_mode', _DEFAULT_SCOPE_MODE),
            rule.get('permission_level', _DEFAULT_PERMISSION_LEVEL),
            rule.get('is_denied', _DEFAULT_IS_DENIED),
            rule.get('inherit_to_children', _DEFAULT_INHERIT_TO_CHILDREN),
            rule.get('propagate_to_parents', _DEFAULT_PROPAGATE_TO_PARENTS),
            rule.get('_source', 'bo_yaml'),
            now,
            now,
        )
        self._ds.execute(sql, params)


# ============================================================================
# 辅助函数
# ============================================================================

def _is_truthy(value: Any) -> bool:
    """判断 value 是否�?truthy (兼容 bool/int/str)"""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes')
    return bool(value)
