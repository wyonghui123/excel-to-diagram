"""
rls/loader.py - RLS 规则加载器

支持：
- YAML 声明式配置（与 meta_object.authorization 对齐）
- 内存缓存（按文件 mtime 失效）
- 热加载接口（hot_reload.py 调用 clear_cache）
- 优雅降级（YAML 错误时返回空，不影响业务）

rls_rules/*.yaml Schema:
  entity: order
  row_filters:
    - applies_to: [role:user, role:viewer]
      condition: "user.company_id == order.company_id"
  field_masks:
    - field: phone
      mask: "***-****-{}"
      applies_to: [role:user, role:viewer, role:ai-agent]
  actions:
    create: [role:admin, role:manager]
    read: [role:admin, role:manager, role:user, role:viewer, role:ai-agent]
    update: [role:admin, role:manager]
    delete: [role:admin]
"""
import os
import glob
import logging
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class RLSLoader:
    """RLS 规则加载器（单例）

    单一事实源：rls_rules/ 目录下所有 .yaml 文件
    缓存策略：按文件 mtime 失效（修改后下次 load_all 自动重载）
    """

    _instance: Optional['RLSLoader'] = None
    _rules: Dict[str, dict] = {}
    _mtimes: Dict[str, float] = {}
    _rules_dir: Optional[str] = None

    def __init__(self):
        # 允许直接实例化，但推荐用 get_loader()
        pass

    @classmethod
    def get_instance(cls, rules_dir: Optional[str] = None) -> 'RLSLoader':
        if cls._instance is None:
            cls._instance = cls()
        if rules_dir and cls._instance._rules_dir != rules_dir:
            cls._instance.set_rules_dir(rules_dir)
        return cls._instance

    def set_rules_dir(self, rules_dir: str) -> None:
        if self._rules_dir != rules_dir:
            self._rules_dir = rules_dir
            self._rules = {}
            self._mtimes = {}
            logger.info(f"[RLS] rules_dir set to: {rules_dir}")

    def load_all(self) -> Dict[str, dict]:
        """加载所有规则（带 mtime 缓存）

        行为：
        1. 遍历 rls_rules/*.yaml
        2. 检查每个文件 mtime
        3. mtime 未变 → 跳过（缓存命中）
        4. mtime 变化 → 重新加载
        5. 新文件 → 加载

        Returns:
            Dict[entity_name, rule_dict]
        """
        if not self._rules_dir or not os.path.isdir(self._rules_dir):
            return {}

        for yaml_file in glob.glob(os.path.join(self._rules_dir, '*.yaml')):
            try:
                mtime = os.path.getmtime(yaml_file)
            except OSError:
                continue
            if yaml_file in self._mtimes and self._mtimes[yaml_file] == mtime:
                continue  # 缓存命中
            self._load_one(yaml_file, mtime)
        return self._rules

    def _load_one(self, yaml_file: str, mtime: float) -> None:
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                logger.warning(f"[RLS] {yaml_file} top-level not a dict, skipped")
                return
            entity = data.get('entity')
            if not entity:
                logger.warning(f"[RLS] {yaml_file} missing 'entity' field, skipped")
                return
            self._rules[entity] = data
            self._mtimes[yaml_file] = mtime
            logger.info(f"[RLS] Loaded entity '{entity}': {yaml_file}")
        except yaml.YAMLError as e:
            logger.error(f"[RLS] YAML parse error in {yaml_file}: {e}")
        except Exception as e:
            logger.error(f"[RLS] Failed to load {yaml_file}: {e}")

    def get_row_filters(self, entity: str, role: str) -> List[dict]:
        """获取行级过滤规则（适用于当前 entity + role）"""
        rules = self.load_all().get(entity, {})
        filters = rules.get('row_filters', []) or []
        return [f for f in filters if role in f.get('applies_to', [])]

    def get_field_masks(self, entity: str, role: str) -> List[dict]:
        """获取字段脱敏规则"""
        rules = self.load_all().get(entity, {})
        masks = rules.get('field_masks', []) or []
        return [m for m in masks if role in m.get('applies_to', [])]

    def get_allowed_actions(self, entity: str, role: str) -> List[str]:
        """获取允许的操作列表（CRUD + business）"""
        rules = self.load_all().get(entity, {})
        actions = rules.get('actions', {}) or {}
        return [act for act, roles in actions.items() if role in (roles or [])]

    def get_entities(self) -> List[str]:
        """获取所有已加载的 entity 名"""
        return list(self.load_all().keys())

    def clear_cache(self) -> None:
        """清空缓存（热加载用）"""
        self._rules = {}
        self._mtimes = {}
        logger.info("[RLS] cache cleared")

    def has_rule_for(self, entity: str) -> bool:
        """检查某 entity 是否有 RLS 规则"""
        return entity in self.load_all()


# ==================== 公开 API ====================

def get_loader(rules_dir: Optional[str] = None) -> RLSLoader:
    return RLSLoader.get_instance(rules_dir)

def get_row_filters(entity: str, role: str, rules_dir: Optional[str] = None) -> List[dict]:
    return get_loader(rules_dir).get_row_filters(entity, role)

def get_field_masks(entity: str, role: str, rules_dir: Optional[str] = None) -> List[dict]:
    return get_loader(rules_dir).get_field_masks(entity, role)

def get_allowed_actions(entity: str, role: str, rules_dir: Optional[str] = None) -> List[str]:
    return get_loader(rules_dir).get_allowed_actions(entity, role)

def clear_cache() -> None:
    get_loader().clear_cache()
